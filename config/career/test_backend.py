"""Focused backend contract tests; all writes are confined to temporary fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('career_backend', Path(__file__).with_name('backend.py'))
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
CONTENT = '# Application draft\n\n' + 'Evidence from my prior work supports the responsibilities of this role and the application will need personal review before any submission.\n'


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.b = backend.Backend(self.root, self.root / 'cache')
        self.b.inventory_path.parent.mkdir(parents=True)
        self.inventory = {'updated_at': '2026-10-07T00:00:00Z', 'jobs': {
            key: {'id': key, 'title': 'Data Scientist', 'company': 'Acme', 'lifecycle': 'active',
                  'user': {'status': 'unseen'}, 'scoring': {'total': 80, 'priority': 'B', 'matches': ['Python']}}
            for key in ('job-a', 'job-b')}}
        self.write_inventory()

    def write_inventory(self):
        self.b.inventory_path.write_text(json.dumps(self.inventory))

    def job(self, key='job-a'):
        return next(j for j in self.b.list()['jobs'] if j['id'] == key)

    def pack(self, request='one', expected='unseen', revision=0, content=CONTENT):
        return self.b.mutate('job-a', pack={'content': content, 'expected': expected,
                                          'expected_revision': revision, 'request_id': request})

    def assert_error(self, code, call):
        with self.assertRaises(backend.Error) as caught:
            call()
        self.assertEqual(caught.exception.payload['code'], code)
        return caught.exception.payload

    def test_choice_does_not_make_inventory_look_fresh(self):
        before = self.b.list()['inventory_updated_at']
        self.b.mutate('job-a', 'shortlisted', 'unseen', 0)
        after = self.b.list()
        self.assertEqual(before, after['inventory_updated_at'])
        self.assertIsNotNone(after['workspace_updated_at'])

    def test_readonly_and_sanitized(self):
        self.inventory['jobs']['job-a']['title'] = '\x1b[31mTitle\x1b[0m\x00\u202e'
        self.write_inventory()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.job()['title'], 'Title')
        self.b.context('job-a')
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / 'data').exists())

    def test_legacy_override_and_snapshot(self):
        self.inventory['jobs']['job-a']['user']['status'] = 'reviewed'
        self.write_inventory()
        self.b.mutate('job-a', 'shortlisted', 'reviewed', 0)
        self.inventory['jobs']['job-a']['user']['status'] = 'dismissed'
        self.write_inventory()
        self.assertEqual(self.job()['status'], 'shortlisted')
        del self.inventory['jobs']['job-a']
        self.write_inventory()
        self.assertEqual(self.job()['lifecycle'], 'missing')
        self.assertEqual(self.job()['title'], 'Data Scientist')
        self.assert_error('inactive_guard', lambda: self.b.mutate('job-a', 'applied', 'shortlisted', 1))

    def test_cas_and_repeated_status(self):
        first = self.b.mutate('job-a', 'reviewed', 'unseen', 0)
        self.assert_error('conflict', lambda: self.b.mutate('job-a', 'dismissed', 'unseen', 0))
        self.assert_error('conflict', lambda: self.b.mutate('job-a', 'reviewed', 'reviewed', 0))
        self.assertEqual(first, self.b.mutate('job-a', 'reviewed', 'unseen'))
        self.assertEqual(first, self.b.mutate('job-a', 'reviewed', 'reviewed', 1))

    def test_applied_and_inactive_guards(self):
        for lifecycle in ('stale', 'closed', 'expired', 'unknown'):
            self.inventory['jobs']['job-a']['lifecycle'] = lifecycle
            self.write_inventory()
            for target in ('shortlisted', 'applied'):
                self.assert_error('inactive_guard', lambda: self.b.mutate('job-a', target, 'unseen', 0))
            self.assert_error('inactive_guard', self.pack)
        self.inventory['jobs']['job-a']['lifecycle'] = 'active'
        self.write_inventory()
        self.b.mutate('job-a', 'applied', 'unseen', 0)
        for target in backend.STATUSES - {'applied', 'draft'}:
            self.assert_error('applied_guard', lambda: self.b.mutate('job-a', target, 'applied', 1))
        self.inventory['jobs']['job-a']['lifecycle'] = 'closed'
        self.write_inventory()
        self.assert_error('inactive_guard', lambda: self.pack(expected='applied', revision=1))
        self.inventory['jobs']['job-a']['lifecycle'] = 'active'
        self.write_inventory()
        result = self.pack(expected='applied', revision=1)
        self.assertEqual(result['job']['status'], 'applied')
        self.assertEqual(result['job']['revision'], 2)

    def test_versions_replay_and_stale_draft(self):
        first = self.pack()
        self.assertEqual(first, self.pack())
        self.assert_error('request_conflict', lambda: self.pack(content=CONTENT + '\nExtra content.'))
        second = self.pack('two', 'draft', 1, CONTENT + '\nSecond version.')
        self.assertEqual(second['pack_path'], 'Applications/job-a/Application-v002.md')
        self.assertTrue((self.root / first['pack_path']).read_text().endswith(CONTENT))
        self.assertTrue((self.root / first['pack_path']).read_text().startswith('---\ntype: reference\nstatus: draft'))
        self.assertEqual(first, self.pack())
        self.assert_error('conflict', lambda: self.pack('three', 'draft', 1))
        self.assert_error('draft_requires_pack', lambda: self.b.mutate('job-a', 'draft', 'draft', 1))
        self.assertEqual(len(list((self.root / 'Applications/job-a').glob('Application-v*.md'))), 2)
        self.assertTrue((self.root / 'Applications/Applications.md').exists())
        self.assertIn('Application-v002', (self.root / 'Applications/job-a/job-a.md').read_text())

    def test_bad_ids_and_symlinks(self):
        for key in ('../escape', 'job/a', '/tmp/a', '.', '', 'a\n', 'a\\b'):
            self.assert_error('invalid_id', lambda: self.b.mutate(key, 'reviewed', 'unseen'))
            self.assert_error('invalid_id', lambda: self.b.context(key))
        (self.root / 'Applications').symlink_to(self.root / 'elsewhere')
        self.assert_error('unsafe_path', self.pack)
        self.assertFalse(self.b.state_path.exists())

    def test_invalid_pack_and_json(self):
        for content in ('', '# Title', 'words ' * 30):
            self.assert_error('invalid_pack', lambda: self.pack(content=content))
        self.assert_error('invalid_revision', lambda: self.b.mutate('job-a', pack={
            'content': CONTENT, 'expected': 'unseen', 'request_id': 'x'}))
        result = self.cli('save-pack', 'job-a', stdin='{')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['code'], 'invalid_pack')
        self.assertFalse(self.b.state_path.exists())

    def test_malformed_files_never_reset(self):
        self.b.mutate('job-a', 'reviewed', 'unseen')
        for malformed in ('{', '{}', '{"schema_version":1,"jobs":{},"requests":[]}'):
            self.b.state_path.write_text(malformed)
            self.assert_error('invalid_state', lambda: self.b.mutate('job-b', 'reviewed', 'unseen'))
            self.assert_error('invalid_state', self.b.list)
            self.assertEqual(self.b.state_path.read_text(), malformed)
        self.b.state_path.unlink()
        for malformed in ('{', '{}', '{"jobs":{"job-a":null}}'):
            self.b.inventory_path.write_text(malformed)
            self.assert_error('invalid_inventory', self.b.list)
            self.assert_error('invalid_inventory', lambda: self.b.mutate('job-a', 'reviewed', 'unseen'))
            self.assertFalse(self.b.state_path.exists())

    def test_state_commit_failure_retains_orphan(self):
        with patch.object(self.b, 'commit', side_effect=OSError('disk failure')):
            error = self.assert_error('state_write_failed', self.pack)
        orphan = Path(error['orphan_path'])
        self.assertTrue(orphan.read_text().endswith(CONTENT))
        self.assertEqual(self.job()['status'], 'unseen')
        retry = self.pack()
        self.assertTrue(retry['pack_path'].endswith('v002.md'))
        self.assertTrue(orphan.read_text().endswith(CONTENT))

    def test_pack_write_failure_never_commits(self):
        original = Path.open
        def fail(path, *args, **kwargs):
            if args and args[0] == 'x':
                raise OSError('write denied')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', fail):
            self.assert_error('pack_write_failed', self.pack)
        self.assertFalse(self.b.state_path.exists())
        self.assertEqual(self.job()['status'], 'unseen')

    def test_atomic_replace_failure_preserves_state(self):
        self.b.mutate('job-a', 'reviewed', 'unseen')
        original = self.b.state_path.read_bytes()
        with patch.object(backend.os, 'replace', side_effect=OSError('replace failed')):
            self.assert_error('state_write_failed', lambda: self.b.mutate('job-b', 'reviewed', 'unseen'))
        self.assertEqual(self.b.state_path.read_bytes(), original)

    def test_projection_warning_and_recovery(self):
        original = backend.atomic_write
        def fail_board(path, content):
            if path.name == 'Career Board.md':
                raise OSError('board unavailable')
            return original(path, content)
        with patch.object(backend, 'atomic_write', fail_board):
            result = self.pack()
        self.assertTrue(result['committed'])
        self.assertIn('pending', result['warning'])
        self.assertEqual(self.job()['status'], 'draft')
        self.assertIn('board_warning', self.b.list())
        self.b.refresh_board()
        self.assertNotIn('warning', self.b.list())
        (self.root / 'Career Board.md').unlink()
        self.pack()
        self.assertNotIn('warning', self.b.list())
        self.assertFalse((self.root / 'Application Pipeline.md').exists())

    def test_replay_surfaces_continuing_projection_failure(self):
        with patch.object(self.b, 'project', return_value='Career Board projection pending'):
            first = self.pack()
            replay = self.pack()
        self.assertEqual(first, replay)
        self.assertIn('pending', replay['warning'])
        self.assertEqual(self.job()['revision'], 1)

    def test_same_legacy_status_becomes_owned_decision(self):
        self.inventory['jobs']['job-a']['user']['status'] = 'reviewed'
        self.write_inventory()
        first = self.b.mutate('job-a', 'reviewed', 'reviewed', 0)
        self.assertEqual(first['job']['revision'], 1)
        del self.inventory['jobs']['job-a']
        self.write_inventory()
        self.assertEqual(self.job()['status'], 'reviewed')

    def test_malformed_value_types_stay_json_errors(self):
        self.inventory['jobs']['job-a']['user']['status'] = []
        self.write_inventory()
        result = self.cli('list')
        self.assertEqual(json.loads(result.stdout)['code'], 'invalid_inventory')
        self.assertEqual(result.stderr, '')
        self.inventory['jobs']['job-a']['user']['status'] = 'unseen'
        self.inventory['updated_at'] = []
        self.write_inventory()
        self.assert_error('invalid_inventory', self.b.list)
        self.inventory['updated_at'] = None
        self.write_inventory()
        self.assert_error('invalid_status', lambda: self.b.mutate('job-a', 'reviewed', []))

    def test_dates_history_and_dismissed_guard(self):
        self.assert_error('draft_requires_pack', lambda: self.b.mutate('job-a', 'draft', 'unseen', 0))
        self.b.mutate('job-a', 'dismissed', 'unseen', 0)
        self.assert_error('dismissed_guard', lambda: self.b.mutate('job-a', 'applied', 'dismissed', 1))
        self.b.mutate('job-a', 'reviewed', 'dismissed', 1)
        result = self.b.mutate('job-a', 'applied', 'reviewed', 2)
        applied = result['job']['applied_at']
        self.assertTrue(applied.startswith(datetime.now(timezone.utc).date().isoformat()))
        self.assertEqual(self.job()['applied_at'], applied)
        self.pack(expected='applied', revision=3)
        self.assertEqual(self.job()['applied_at'], applied)
        decision = self.b.state()['jobs']['job-a']
        self.assertEqual(len(decision['history']), 4)
        self.assertEqual(decision['history'][-1]['action'], 'save-pack')
        self.assertIn('Applied: ' + applied[:10], (self.root / 'Career Board.md').read_text())

    def test_inactive_redraft_rejected_but_exact_replay_allowed(self):
        first = self.pack()
        self.inventory['jobs']['job-a']['lifecycle'] = 'closed'
        self.write_inventory()
        self.assert_error('inactive_guard', lambda: self.pack('two', 'draft', 1))
        self.assertEqual(first, self.pack())
        self.assertEqual(self.job()['revision'], 1)

    def test_context_bounded_cache_expiry(self):
        for name in backend.PROFILE:
            (self.root / name).write_text('Profile evidence\n')
        (self.root / 'Career Workflow.md').write_text('x' * 20000)
        self.b.cache.mkdir()
        path = self.b.cache / 'job-a.json'
        def cache(age):
            path.write_text(json.dumps({'job_id': 'job-a', 'description': 'Raw private description',
                'cached_at': (datetime.now(timezone.utc) - timedelta(days=age)).isoformat()}))
        cache(1)
        result = self.b.context('job-a')
        self.assertEqual(result['description'], 'Raw private description')
        self.assertEqual(len(result['profile']['Career Workflow.md']), 16000)
        self.assertEqual(result['profile_truncated'], ['Career Workflow.md'])
        cache(8)
        self.assertNotIn('description', self.b.context('job-a'))
        self.pack()
        self.assertNotIn('Raw private description', self.b.state_path.read_text())

    def cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(Path(backend.__file__)), '--root', str(self.root), *args],
                              input=stdin, capture_output=True, text=True)

    def test_cli_contract(self):
        self.assertEqual(json.loads(self.cli('list').stdout)['jobs'][0]['revision'], 0)
        result = self.cli('status', 'job-a', 'reviewed', '--expected', 'unseen', '--expected-revision', '0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['job']['revision'], 1)
        for args in [('bad-command',), ('status', 'job-a', 'reviewed'), ('context', 'missing')]:
            result = self.cli(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('code', json.loads(result.stdout))
            self.assertEqual(result.stderr, '')

    def test_concurrent_processes_preserve_writes(self):
        processes = [subprocess.Popen([sys.executable, backend.__file__, '--root', str(self.root),
                     'status', key, 'reviewed', '--expected', 'unseen', '--expected-revision', '0'],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for key in ('job-a', 'job-b')]
        for process in processes:
            out, err = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, (out, err))
        self.assertEqual({j['status'] for j in self.b.list()['jobs']}, {'reviewed'})
        processes = [subprocess.Popen([sys.executable, backend.__file__, '--root', str(self.root),
                     'status', 'job-a', target, '--expected', 'reviewed', '--expected-revision', '1'],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for target in ('dismissed', 'shortlisted')]
        codes = []
        for process in processes:
            process.communicate(timeout=10)
            codes.append(process.returncode)
        self.assertEqual(sorted(codes), [0, 1])
        self.assertEqual(self.job()['revision'], 2)


if __name__ == '__main__':
    unittest.main()
