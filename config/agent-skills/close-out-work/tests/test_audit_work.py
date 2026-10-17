import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "audit_work", Path(__file__).resolve().parents[1] / "scripts/audit_work.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="close-out-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "dev")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "file").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.git("branch", "main")

    def git(self, *args, repo=None):
        return module.git(repo or self.repo, *args)

    def tree(self, name="topic", path="task with spaces"):
        path = self.root / path
        self.git("worktree", "add", "-b", name, str(path), "dev")
        return path

    def change(self, path):
        (path / "feature").write_text("feature\n")
        self.git("add", ".", repo=path)
        self.git("commit", "-m", "feature", repo=path)

    def row(self, path, result=None):
        result = result or module.audit(self.repo, "dev", "main")
        return next(r for r in result["worktrees"] if r["path"] == str(path))

    def test_merged_worktree_and_release_gap(self):
        path = self.tree()
        self.change(path)
        self.git("merge", "--ff-only", "topic")
        result = module.audit(self.repo, "dev", "main")
        self.assertTrue(self.row(path, result)["integrated_by_ancestry"])
        self.assertEqual(self.row(path, result)["classification"], "candidate-pending-ownership-and-activity")
        self.assertEqual(result["release"]["target_vs_release"], {"left_only": 1, "right_only": 0})

    def test_unmerged_and_squashed_need_external_proof(self):
        path = self.tree()
        self.change(path)
        self.assertFalse(self.row(path)["integrated_by_ancestry"])
        self.git("merge", "--squash", "topic")
        self.git("commit", "-m", "squashed feature")
        self.assertFalse(self.row(path)["integrated_by_ancestry"])
        self.assertIn("integration-unproven", self.row(path)["reasons"])

    def test_dirty_untracked_ignored_are_preserved(self):
        path = self.tree()
        (path / "file").write_text("edited")
        (path / "notes\nwith newline").write_text("unique work")
        (path / ".gitignore").write_text("private.data\n")
        (path / "private.data").write_text("retained")
        row = self.row(path)
        self.assertIn("local-files-require-review", row["reasons"])
        self.assertEqual({x["status"] for x in row["files"]}, {" M", "??", "!!"})
        self.assertIn("notes\nwith newline", [x["path"] for x in row["files"]])

    def test_locked_and_detached_are_not_candidates(self):
        path = self.tree(path="task\nwith newline")
        self.git("checkout", "--detach", repo=path)
        self.git("worktree", "lock", str(path))
        row = self.row(path)
        self.assertIn("locked", row["reasons"])
        self.assertIn("detached", row["reasons"])

    def test_missing_registered_path_fails_closed(self):
        path = self.tree()
        path.rename(self.root / "moved")
        self.assertIn("inspection-failed", self.row(path)["reasons"])

    def test_staged_rename_is_parsed(self):
        path = self.tree()
        self.git("mv", "file", "renamed file", repo=path)
        row = self.row(path)
        self.assertEqual(row["files"], [{"status": "R ", "path": "renamed file", "original_path": "file"}])

    def test_upstream_divergence_and_missing_ref(self):
        self.git("config", "remote.origin.url", str(self.root / "nonexistent-remote"))
        self.git("config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        self.git("update-ref", "refs/remotes/origin/dev", "dev")
        self.git("branch", "--set-upstream-to", "origin/dev", "dev")
        self.change(self.repo)
        result = module.audit(self.repo, "dev")
        branch = next(b for b in result["branches"] if b["ref"] == "refs/heads/dev")
        self.assertEqual(branch["versus_upstream"], {"left_only": 1, "right_only": 0})
        self.git("update-ref", "-d", "refs/remotes/origin/dev")
        branch = next(b for b in module.audit(self.repo, "dev")["branches"] if b["ref"] == "refs/heads/dev")
        self.assertEqual(branch["upstream_status"], "missing-local-ref")

    def test_audit_does_not_change_refs_worktrees_or_files(self):
        path = self.tree()
        (path / "untracked").write_text("keep")
        before = (self.git("show-ref"), self.git("worktree", "list", "--porcelain"), self.git("status", "--porcelain", repo=path))
        module.audit(self.repo, "dev", "main")
        after = (self.git("show-ref"), self.git("worktree", "list", "--porcelain"), self.git("status", "--porcelain", repo=path))
        self.assertEqual(before, after)
        self.assertEqual((path / "untracked").read_text(), "keep")

    def test_invalid_target_exits_without_report(self):
        result = subprocess.run(
            ["python", str(Path(module.__file__)), "--repo", str(self.repo), "--target", "missing"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_remote_only_branch_and_protected_worktree(self):
        self.git("update-ref", "refs/remotes/origin/old-task", "dev")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/old-task")
        path = self.root / "release-checkout"
        self.git("worktree", "add", str(path), "main")
        result = module.audit(self.repo, "dev", "main")
        self.assertEqual([r["ref"] for r in result["remote_tracking_branches"]], ["refs/remotes/origin/old-task"])
        self.assertIn("integration-or-protected-branch", self.row(path, result)["reasons"])


if __name__ == "__main__":
    unittest.main()
