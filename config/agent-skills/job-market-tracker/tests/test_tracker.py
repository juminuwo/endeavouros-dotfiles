import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "job_market_tracker.py"
SPEC = importlib.util.spec_from_file_location("job_market_tracker", MODULE_PATH)
tracker_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(tracker_module)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class TrackerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "vault"
        self.cache = base / "cache"
        self.credentials = base / "credentials.json"
        self.root.mkdir(parents=True)
        (self.root / "job-market-config.json").write_text(json.dumps({
            "queries": ["Senior Applied Scientist"],
            "sources": {
                "greenhouse": {"enabled": True},
                "lever": {"enabled": True},
                "reed": {"enabled": False},
                "adzuna": {"enabled": False},
            },
            "ats": {"greenhouse": [], "lever": []},
        }))
        (self.root / "match-profile.json").write_text(json.dumps({"positioning": "test"}))
        self.tracker = tracker_module.Tracker(self.root, self.credentials, self.cache)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, source="greenhouse", source_id="1", description="Production sensor ML " * 50, full=True):
        return tracker_module.raw_job(
            source, source_id, "Senior Applied Scientist", "Acme", "London, UK",
            f"https://example.test/jobs/{source_id}", description,
            tracker_module.iso_now(), None, "hybrid", "full-time", None, full,
        )

    def score(self, job_id, total="A"):
        if total == "A":
            components = {"role_fit": 23, "technical_alignment": 23, "delivery_ownership": 18, "domain_alignment": 13, "logistics": 13}
        elif total == "B":
            components = {"role_fit": 20, "technical_alignment": 20, "delivery_ownership": 16, "domain_alignment": 10, "logistics": 12}
        else:
            components = {"role_fit": 12, "technical_alignment": 12, "delivery_ownership": 11, "domain_alignment": 9, "logistics": 11}
        return {
            "job_id": job_id,
            "lane": "applied-ml-operations",
            "components": components,
            "matches": ["sensor ML"],
            "gaps": ["none stated"],
            "uncertainties": ["salary"],
            "summary": "Applied ML role.",
            "critical_unknown": False,
            "hard_blocker": False,
            "hard_blocker_reason": None,
        }

    def start_workflow(self, run_id="run-test"):
        pending = self.tracker.pending_count()
        self.tracker.state["workflow_run"] = {
            "id": run_id,
            "status": "scoring" if pending else "ready-to-finalize",
            "started_at": tracker_module.iso_now(),
            "pending_count": pending,
            "batches_completed": 0,
            "scores_applied": 0,
            "resume_count": 0,
            "error": None,
        }
        return run_id


class NormalizerTests(TrackerTestCase):
    def test_greenhouse_normalization_strips_html(self):
        item = {"id": 7, "title": "CV Engineer", "location": {"name": "London"}, "absolute_url": "https://x/7", "content": "<p>Build <b>vision</b>.</p>", "updated_at": "2026-08-11T09:00:00Z"}
        result = self.tracker._normalize_greenhouse(item, "Vision Co")
        self.assertEqual(result["description"], "Build vision.")
        self.assertTrue(result["full_description"])

    def test_lever_normalization_handles_millisecond_timestamp_and_salary_unknown(self):
        item = {"id": "abc", "text": "Edge AI Engineer", "createdAt": 1786438800000, "hostedUrl": "https://x/abc", "workplaceType": "hybrid", "categories": {"location": "London", "commitment": "Full-time"}, "descriptionPlain": "Deploy models", "lists": []}
        result = self.tracker._normalize_lever(item, "Edge Co")
        self.assertEqual(result["salary"], None)
        self.assertEqual(tracker_module.normalized_iso(result["posted_at"]), "2026-08-11T09:00:00Z")

    def test_reed_salary_and_description(self):
        result = self.tracker._normalize_reed({"jobId": 4, "jobTitle": "Senior Data Scientist", "employerName": "R", "locationName": "UK", "jobUrl": "https://x/4", "jobDescription": "x" * 600, "minimumSalary": 70000, "maximumSalary": 90000, "currency": "GBP"})
        self.assertEqual(result["salary"]["min"], 70000)
        self.assertTrue(result["full_description"])

    def test_ats_filter_uses_role_title_not_incidental_description_keyword(self):
        unrelated = self.record()
        unrelated["title"] = "Senior CFD Engineer"
        unrelated["description"] = "Collaborate with the machine learning team"
        self.assertFalse(self.tracker._ats_candidate(unrelated))
        relevant = self.record()
        relevant["title"] = "Research Scientist, Multimodal Models"
        self.assertTrue(self.tracker._ats_candidate(relevant))


class RetrievalTests(TrackerTestCase):
    def test_fetch_retries_transient_error(self):
        calls = []

        def opener(_request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise urllib.error.URLError("temporary")
            return FakeResponse({"ok": True})

        self.tracker.opener = opener
        original_sleep = tracker_module.time.sleep
        tracker_module.time.sleep = lambda _seconds: None
        try:
            self.assertEqual(self.tracker.fetch_json("https://example.test"), {"ok": True})
        finally:
            tracker_module.time.sleep = original_sleep
        self.assertEqual(len(calls), 2)

    def test_auth_error_message_does_not_include_secret(self):
        def opener(_request, timeout):
            raise urllib.error.HTTPError("https://example.test", 401, "bad", {}, io.BytesIO(b""))

        self.tracker.opener = opener
        with self.assertRaisesRegex(RuntimeError, "authentication rejected"):
            self.tracker.fetch_json("https://example.test?api_key=secret")

    def test_reed_deduplicates_queries_and_skips_unrelated_titles(self):
        search = {
            "results": [
                {"jobId": 1, "jobTitle": "Senior Data Scientist", "employerName": "A", "locationName": "London", "jobUrl": "https://x/1"},
                {"jobId": 2, "jobTitle": "Senior CFD Engineer", "employerName": "B", "locationName": "London", "jobUrl": "https://x/2"},
            ]
        }
        detail_calls = []

        def fetch(url, headers=None):
            if "/jobs/" in url:
                detail_calls.append(url)
                return {"jobId": 1, "jobDescription": "production ML " * 50}
            return search

        self.tracker.fetch_json = fetch
        results = self.tracker.collect_reed({"reed": {"api_key": "not-logged"}})
        self.assertEqual(len(results), 1)
        self.assertEqual(len(detail_calls), 1)

    def test_adzuna_gb_query_does_not_add_redundant_country_filter(self):
        requested_urls = []

        def fetch(url, headers=None):
            requested_urls.append(url)
            return {"results": []}

        self.tracker.fetch_json = fetch
        self.tracker.collect_adzuna({"adzuna": {"app_id": "id", "app_key": "key"}})
        self.assertEqual(len(requested_urls), 1)
        self.assertNotIn("where=", requested_urls[0])


class DeduplicationTests(TrackerTestCase):
    def test_same_source_and_url_are_idempotent(self):
        self.tracker._merge([self.record(), self.record()])
        self.assertEqual(len(self.tracker.state["jobs"]), 1)
        job = next(iter(self.tracker.state["jobs"].values()))
        self.assertEqual(len(job["sources"]), 1)

    def test_exact_company_title_location_merges_cross_source(self):
        first = self.record("adzuna", "a")
        second = self.record("greenhouse", "g")
        second["url"] = "https://ats.test/g"
        self.tracker._merge([first, second])
        self.assertEqual(len(self.tracker.state["jobs"]), 1)
        job = next(iter(self.tracker.state["jobs"].values()))
        self.assertEqual({ref["source"] for ref in job["sources"]}, {"adzuna", "greenhouse"})
        self.assertEqual(job["canonical_url"], "https://ats.test/g")

    def test_lower_priority_duplicate_does_not_replace_ats_description(self):
        ats = self.record("greenhouse", "g", description="preferred ATS description")
        board = self.record("reed", "r", description="short board description")
        board["url"] = "https://board.test/r"
        self.tracker._merge([ats, board])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.assertEqual(job["description_source"], "greenhouse")
        self.assertEqual(job["content_hash"], tracker_module.short_hash("preferred ATS description", 32))

    def test_same_source_distinct_ids_with_same_fingerprint_stay_distinct(self):
        first = self.record("reed", "one", description="first vacancy")
        second = self.record("reed", "two", description="second vacancy")
        second["url"] = "https://example.test/jobs/two"
        self.tracker._merge([first, second])
        self.assertEqual(len(self.tracker.state["jobs"]), 2)

    def test_cross_source_fingerprint_does_not_merge_when_ambiguous(self):
        first = self.record("reed", "one")
        second = self.record("reed", "two")
        second["url"] = "https://example.test/jobs/two"
        ats = self.record("greenhouse", "ats")
        ats["url"] = "https://ats.test/jobs/ats"
        self.tracker._merge([first, second, ats])
        self.assertEqual(len(self.tracker.state["jobs"]), 3)


class ScoringTests(TrackerTestCase):
    def test_thresholds_caps_and_alert_once(self):
        self.tracker._merge([self.record()])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.tracker.apply_scores([self.score(job["id"], "A")], "fixture-model")
        self.assertEqual(job["scoring"]["priority"], "A")
        self.assertTrue(job["alert"]["pending"])
        self.tracker.finalize_run()
        self.tracker.mark_alerted([job["id"]])
        changed = self.record(description="Changed production sensor ML " * 50)
        self.tracker._merge([changed])
        run_id = self.start_workflow("run-changed")
        self.tracker.apply_scores({"run_id": run_id, "scores": [self.score(job["id"], "A")]}, "fixture-model")
        self.assertFalse(job["alert"]["pending"], "same priority must not re-alert")

    def test_incomplete_description_caps_a_to_b(self):
        self.tracker._merge([self.record(full=False)])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.tracker.apply_scores([self.score(job["id"], "A")], None)
        self.assertEqual(job["scoring"]["priority"], "B")
        self.assertIn("incomplete description", job["scoring"]["caps"])

    def test_schema_rejects_component_over_maximum(self):
        self.tracker._merge([self.record()])
        job = next(iter(self.tracker.state["jobs"].values()))
        score = self.score(job["id"])
        score["components"]["role_fit"] = 26
        with self.assertRaisesRegex(ValueError, "role_fit"):
            self.tracker.apply_scores([score], None)

    def test_user_state_and_override_survive_refresh_and_can_clear(self):
        self.tracker._merge([self.record()])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.tracker.apply_scores([self.score(job["id"], "B")], None)
        self.tracker.finalize_run()
        self.tracker.set_status(job["id"], "shortlisted", 5, "good", "A")
        self.tracker.set_status(job["id"], "reviewed", None, None, "none")
        self.tracker._merge([self.record(description="updated " * 100)])
        self.assertEqual(job["user"]["status"], "reviewed")
        self.assertIsNone(job["user"]["priority_override"])


class PersistenceTests(TrackerTestCase):
    def test_dashboard_validation_and_purge(self):
        self.tracker._merge([self.record("lever", "l")])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.tracker.apply_scores([self.score(job["id"], "C")], None)
        self.tracker.finalize_run()
        dashboard = self.tracker.dashboard_path.read_text()
        self.assertIn("## Run and source health", dashboard)
        self.assertIn("## Calibration", dashboard)
        self.assertIn("### C · 55 —", dashboard)
        self.assertNotIn("| Priority | Score |", dashboard)
        self.assertEqual(self.tracker.validate(), [])
        result = self.tracker.purge_source("lever")
        self.assertEqual(result["removed_jobs"], 1)

    def test_validation_rejects_obsidian_incompatible_short_separator(self):
        self.tracker.dashboard_path.write_text(
            "# Job Market Dashboard\n\n| Pri | Score |\n| --: | ---: |\n| A | 90 |\n",
            encoding="utf-8",
        )
        self.assertTrue(any("at least three hyphens" in error for error in self.tracker.validate()))

    def test_fixture_collect_twice_is_idempotent_and_records_health(self):
        record = self.record()
        self.tracker.collect_greenhouse = lambda: [record.copy()]
        self.tracker.collect_lever = lambda: []
        self.tracker.dashboard_path.write_text("unchanged until finalization", encoding="utf-8")
        first = self.tracker.collect()
        self.assertEqual(
            self.tracker.dashboard_path.read_text(encoding="utf-8"),
            "unchanged until finalization",
        )
        with self.assertRaisesRegex(RuntimeError, "unfinished scoring workflow"):
            self.tracker.collect()
        job = next(iter(self.tracker.state["jobs"].values()))
        run_id = self.tracker.state["workflow_run"]["id"]
        self.tracker.apply_scores({"run_id": run_id, "scores": [self.score(job["id"], "C")]}, None)
        self.tracker.finalize_run()
        second = self.tracker.collect()
        self.assertEqual(first["new_jobs"], 1)
        self.assertEqual(second["new_jobs"], 0)
        self.assertEqual(len(self.tracker.state["jobs"]), 1)
        self.assertEqual(self.tracker.state["source_health"]["greenhouse"]["status"], "ok")
        self.assertEqual(len(tracker_module.read_history(self.tracker.history_path)), 2)

    def test_multi_batch_run_must_drain_before_finalize_or_alert(self):
        for index in range(3):
            self.tracker._merge([self.record("greenhouse", str(index))])
        run_id = self.start_workflow()
        first = self.tracker.pending(2)
        self.assertEqual(first["pending_count"], 3)
        self.assertEqual(len(first["jobs"]), 2)
        first_scores = [self.score(item["job_id"], "B") for item in first["jobs"]]
        result = self.tracker.apply_scores({"run_id": run_id, "scores": first_scores}, None)
        self.assertEqual(result["pending_count"], 1)
        with self.assertRaisesRegex(RuntimeError, "cannot finalize"):
            self.tracker.finalize_run()
        with self.assertRaisesRegex(RuntimeError, "cannot inspect alerts"):
            self.tracker.alerts()
        second = self.tracker.pending(2)
        result = self.tracker.apply_scores(
            {"run_id": run_id, "scores": [self.score(second["jobs"][0]["job_id"], "B")]},
            None,
        )
        self.assertEqual(result["pending_count"], 0)
        final = self.tracker.finalize_run()
        self.assertEqual(final["status"], "complete")
        self.assertEqual(final["batches_completed"], 2)
        self.assertEqual(len(self.tracker.alerts()["jobs"]), 3)

    def test_collect_rejects_pending_jobs_even_if_workflow_claims_complete(self):
        self.tracker._merge([self.record()])
        self.tracker.state["workflow_run"] = {"id": "run-corrupt", "status": "complete"}
        with self.assertRaisesRegex(RuntimeError, "pending=1"):
            self.tracker.collect()

    def test_failed_run_is_resumable(self):
        self.tracker._merge([self.record()])
        self.start_workflow()
        failed = self.tracker.fail_run("model timeout")
        self.assertEqual(failed["status"], "failed")
        with self.assertRaisesRegex(RuntimeError, "run resume-run"):
            self.tracker.pending(30)
        resumed = self.tracker.resume_run()
        self.assertEqual(resumed["status"], "scoring")
        self.assertEqual(len(self.tracker.pending(30)["jobs"]), 1)

    def test_stale_score_batch_cannot_mutate_new_run(self):
        self.tracker._merge([self.record()])
        self.start_workflow("run-current")
        job = next(iter(self.tracker.state["jobs"].values()))
        with self.assertRaisesRegex(ValueError, "run_id does not match"):
            self.tracker.apply_scores({"run_id": "run-old", "scores": [self.score(job["id"])]}, None)
        self.assertEqual(self.tracker.pending_count(), 1)

    def test_ats_listing_closes_after_two_complete_missing_runs(self):
        self.tracker._merge([self.record("greenhouse", "gone")])
        job = next(iter(self.tracker.state["jobs"].values()))
        self.tracker._update_lifecycle({"greenhouse"}, set())
        self.assertEqual(job["lifecycle"], "active")
        self.tracker._update_lifecycle({"greenhouse"}, set())
        self.assertEqual(job["lifecycle"], "closed")


if __name__ == "__main__":
    unittest.main()
