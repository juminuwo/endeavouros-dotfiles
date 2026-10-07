import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'config/bin/codex-session-restart'
loader = importlib.machinery.SourceFileLoader('restart', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
r = importlib.util.module_from_spec(spec)
loader.exec_module(r)


def entry():
    return {'socket': '/tmp/kitty-test', 'window': 7, 'shell_pid': 10, 'shell_start': '100',
            'pid': 20, 'start': '200', 'session': {'id': '01a0fc17-136d-7220-b7e0-73b22b657c40', 'cwd': '/repo'}}


def version(cli='new', daemon='new'):
    return {'status': 'running', 'cliVersion': cli, 'managedCodexVersion': daemon, 'appServerVersion': daemon}


class RestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for obj, name, value in [(r, 'STATE', root / 'desktop-session/codex-restart'),
                                 (r, 'JOURNAL', root / 'desktop-session/codex-restart.json'),
                                 (r.ds, 'STATE', root / 'desktop-session'),
                                 (r.ps, 'STATE', root / 'project-switch'),
                                 (r.ps, 'LOCK', str(root / 'project.lock'))]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        r.STATE.mkdir(parents=True)
        r.ps.STATE.mkdir()

    def test_cancel_and_unrecognized_answer_have_no_effect(self):
        for code, text in [(1, ''), (0, 'Cancel\n'), (0, 'yes\n')]:
            with self.subTest(text=text), patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, text, '')), patch.object(r, 'command') as command:
                r.request()
                command.assert_not_called()

    def test_confirmation_starts_detached_persistent_worker(self):
        with patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, r.YES + '\n', '')) as rofi, patch.object(r, 'command') as command, patch.object(r.ds, 'notify'):
            r.request()
        self.assertTrue(rofi.call_args.kwargs['input'].startswith('Cancel\n'))
        args = command.call_args.args
        self.assertIn('--property=RemainAfterExit=yes', args)
        self.assertIn('--property=Type=oneshot', args)
        self.assertIn('--no-block', args)
        self.assertEqual(args[-2:], (r.SCRIPT, 'run'))

    def test_version_notice_is_deduplicated_and_rearmed_after_alignment(self):
        with patch.object(r, 'versions', return_value=version('new', 'old')) as versions, patch.object(r.ds, 'notify') as notify:
            r.check_update()
            r.check_update()
            self.assertEqual(notify.call_count, 1)
            versions.return_value = version()
            r.check_update()
            self.assertFalse((r.STATE / 'notified.json').exists())
            versions.return_value = version('newer', 'new')
            r.check_update()
            self.assertEqual(notify.call_count, 2)

    def test_failed_initial_save_never_stops_clients(self):
        with patch.object(r.ps, 'desktop_id', return_value='desktop'), patch.object(r, 'capture', return_value=[entry()]), patch.object(r.ds, 'save', side_effect=RuntimeError('capture failed')), patch.object(r, 'execute') as execute, patch.object(r.ds, 'notify'):
            r.run()
        execute.assert_not_called()
        self.assertFalse(r.JOURNAL.exists())

    def test_sessions_changing_during_save_stop_nothing(self):
        with patch.object(r.ps, 'desktop_id', return_value='desktop'), patch.object(r, 'capture', side_effect=[[entry()], []]), patch.object(r.ds, 'save'), patch.object(r, 'execute') as execute, patch.object(r.ds, 'notify'):
            r.run()
        execute.assert_not_called()
        self.assertFalse(r.JOURNAL.exists())

    def test_partial_restart_freezes_both_snapshot_paths(self):
        r.ps.atomic_json(r.JOURNAL, {'desktop': 'desktop', 'phase': 'updating-server', 'entries': [entry()]})
        with self.assertRaisesRegex(RuntimeError, 'restart is incomplete'):
            r.ps.check_codex_restart('desktop')
        with patch.object(r.ps, 'desktop_id', return_value='desktop'):
            with self.assertRaisesRegex(RuntimeError, 'restart is incomplete'):
                r.ds.save()
            with self.assertRaisesRegex(RuntimeError, 'restart is incomplete'):
                r.ps.save()
        r.ps.check_codex_restart('new-login')

    def test_retry_uses_journal_without_overwriting_recovery_snapshot(self):
        j = {'desktop': 'desktop', 'phase': 'updating-server', 'entries': [entry()]}
        r.ps.atomic_json(r.JOURNAL, j)
        with patch.object(r.ps, 'desktop_id', return_value='desktop'), patch.object(r, 'capture') as capture, patch.object(r.ds, 'save') as save, patch.object(r, 'execute', side_effect=RuntimeError('update unavailable')) as execute, patch.object(r.ds, 'notify'):
            r.run()
        capture.assert_not_called()
        save.assert_not_called()
        execute.assert_called_once_with(j)
        self.assertEqual(r.ps.read_json(r.JOURNAL)['entries'], j['entries'])
        self.assertEqual(r.ps.read_json(r.JOURNAL)['error'], 'update unavailable')

    def test_replaced_pane_is_rejected(self):
        e = entry()
        with patch.object(r, 'panes', return_value={(e['socket'], e['window']): {'pid': 99}}):
            with self.assertRaisesRegex(RuntimeError, 'disappeared or was replaced'):
                r.pane(e)

    def test_changed_conversation_is_rejected(self):
        e = entry()
        w = {'foreground_processes': [{'pid': 21, 'cmdline': ['codex']}]}
        with patch.object(r, 'pane', return_value=w), patch.object(r.ps.codex_state, 'begin_capture'), patch.object(r.ps, 'codex_session', return_value={'id': 'another'}):
            with self.assertRaisesRegex(RuntimeError, 'another conversation'):
                r.current_pid(e)

    def test_resumed_conversation_is_recognized_on_retry(self):
        e = entry()
        w = {'foreground_processes': [{'pid': 21, 'cmdline': ['codex']}]}
        with patch.object(r, 'pane', return_value=w), patch.object(r.ps.codex_state, 'begin_capture'), patch.object(r.ps, 'codex_session', return_value=e['session']), patch.object(r.ps.codex_state, 'verify_capture'):
            self.assertEqual(r.current_pid(e), 21)

    def test_server_failure_never_sends_resume_command(self):
        j = {'desktop': 'desktop', 'entries': [entry()]}
        with patch.object(r, 'current_pid', return_value=None), patch.object(r, 'client_codex_pids', return_value=set()), patch.object(r, 'wait_shell'), patch.object(r, 'command', side_effect=RuntimeError('daemon failed')), patch.object(r.ps, 'rc') as rc:
            with self.assertRaisesRegex(RuntimeError, 'daemon failed'):
                r.execute(j)
        rc.assert_not_called()
        self.assertEqual(r.ps.read_json(r.JOURNAL)['phase'], 'updating-server')

    def test_success_requires_alignment_and_verified_conversations(self):
        e = entry()
        j = {'desktop': 'desktop', 'entries': [e]}
        with patch.object(r, 'current_pid', return_value=None), patch.object(r, 'client_codex_pids', return_value=set()), patch.object(r, 'wait_shell'), patch.object(r, 'command') as command, patch.object(r, 'versions', return_value=version()), patch.object(r.ps, 'rc') as rc, patch.object(r, 'verify_sessions') as verify:
            r.execute(j)
        self.assertEqual([c.args[3] for c in command.call_args_list], ['stop', 'update', 'start'])
        self.assertIn('--from-cli', command.call_args_list[1].args)
        self.assertEqual(rc.call_count, 1)
        self.assertIn(e['session']['id'], rc.call_args.args[-1])
        verify.assert_called_once_with([e])
        self.assertEqual(r.ps.read_json(r.JOURNAL)['phase'], 'complete')

    def test_version_mismatch_does_not_resume(self):
        with patch.object(r, 'current_pid', return_value=None), patch.object(r, 'client_codex_pids', return_value=set()), patch.object(r, 'wait_shell'), patch.object(r, 'command'), patch.object(r, 'versions', return_value=version('new', 'old')), patch.object(r.ps, 'rc') as rc:
            with self.assertRaisesRegex(RuntimeError, 'versions still differ'):
                r.execute({'entries': [entry()]})
        rc.assert_not_called()

    def test_resume_command_quotes_shell_metacharacters(self):
        e = entry()
        e['session']['cwd'] = '/tmp/space $(touch bad)'
        text = r.resume_command(e)
        self.assertTrue(text.startswith('\x15codex resume '))
        self.assertIn("'/tmp/space $(touch bad)'", text)
        self.assertTrue(text.endswith('\n'))

    def test_original_pid_cannot_switch_conversations_during_retry(self):
        e = entry()
        w = {'foreground_processes': [{'pid': e['pid'], 'cmdline': ['codex']}]}
        with patch.object(r, 'pane', return_value=w), patch.object(r.ps.codex_state, 'begin_capture'), patch.object(r.ps, 'codex_session', return_value={'id': 'different'}):
            with self.assertRaisesRegex(RuntimeError, 'another conversation'):
                r.current_pid(e)

    def capture_fixture(self, base=None, foreground=None, session=None, clients=None):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        e = entry()
        w = {'id': 7, 'pid': 10, 'cmdline': base or ['/usr/bin/zsh'],
             'foreground_processes': foreground or [{'pid': 20, 'cmdline': ['codex']}]}
        stack.enter_context(patch.object(r, 'panes', return_value={(e['socket'], e['window']): w}))
        stack.enter_context(patch.object(r, 'start_time', side_effect=lambda pid: str(pid * 10)))
        stack.enter_context(patch.object(r, 'client_codex_pids', return_value={20} if clients is None else clients))
        stack.enter_context(patch.object(r.ps, 'codex_session', return_value=session or e['session']))
        stack.enter_context(patch.object(r.ps.codex_state, 'begin_capture'))
        stack.enter_context(patch.object(r.ps.codex_state, 'verify_capture'))
        return w

    def test_capture_shell_backed_conversation(self):
        self.capture_fixture()
        self.assertEqual(r.capture(), [entry()])

    def test_capture_restored_pane_helper(self):
        base = ['python3', r.ps.HELPER, 'pane', '--session', entry()['session']['id']]
        self.capture_fixture(base=base, foreground=[
            {'pid': 10, 'cmdline': base}, {'pid': 20, 'cmdline': ['codex']}])
        self.assertEqual(r.capture(), [entry()])

    def test_wrapper_exclusion_is_limited_to_the_known_root_process(self):
        wrapper = ['python3', r.ps.HELPER, 'pane']
        for pid, args in [(11, wrapper), (10, ['python3', '/tmp/job.py']),
                          (10, ['python3', '-c', r.ps.HELPER, 'pane']),
                          (10, ['other', r.ps.HELPER, 'pane'])]:
            with self.subTest(pid=pid, args=args):
                p = {'pid': pid, 'cmdline': args}
                self.assertEqual(r.foreground({'pid': 10, 'foreground_processes': [p]}), [p])

    def test_current_pid_resolves_codex_under_restored_wrapper(self):
        e = entry()
        w = {'pid': 10, 'foreground_processes': [
            {'pid': 10, 'cmdline': ['python3', r.ps.HELPER, 'pane']},
            {'pid': 20, 'cmdline': ['codex']}]}
        with patch.object(r, 'pane', return_value=w), patch.object(r.ps.codex_state, 'begin_capture'), patch.object(r.ps.codex_state, 'verify_capture'), patch.object(r.ps, 'codex_session', return_value=e['session']):
            self.assertEqual(r.current_pid(e), 20)

    def test_wait_shell_requires_wrapper_to_exec_shell(self):
        wrapper = {'pid': 10, 'foreground_processes': [
            {'pid': 10, 'cmdline': ['python3', r.ps.HELPER, 'pane']}]}
        shell = {'pid': 10, 'foreground_processes': [
            {'pid': 10, 'cmdline': ['/usr/bin/zsh']}]}
        with patch.object(r, 'pane', side_effect=[wrapper, shell]), patch.object(r.time, 'sleep') as sleep:
            r.wait_shell(entry())
        sleep.assert_called_once()

    def test_capture_rejects_direct_codex_launch(self):
        self.capture_fixture(base=['codex'])
        with self.assertRaisesRegex(RuntimeError, 'not shell-backed'):
            r.capture()

    def test_capture_rejects_other_foreground_work(self):
        self.capture_fixture(foreground=[{'pid': 20, 'cmdline': ['codex']}, {'pid': 21, 'cmdline': ['make']}])
        with self.assertRaisesRegex(RuntimeError, 'other foreground work'):
            r.capture()

    def test_capture_rejects_custom_home(self):
        self.capture_fixture(session={**entry()['session'], 'home': '/different'})
        with self.assertRaisesRegex(RuntimeError, 'different CODEX_HOME'):
            r.capture()

    def test_capture_rejects_unmanaged_client(self):
        self.capture_fixture(clients={20, 99})
        with self.assertRaisesRegex(RuntimeError, 'outside the supported Kitty'):
            r.capture()

    def test_stop_precedes_server_update_and_resume(self):
        events = []
        e = entry()
        with patch.object(r, 'current_pid', side_effect=[20, 20, None]), patch.object(r, 'client_codex_pids', return_value={20}), patch.object(r.os, 'pidfd_open', return_value=99), patch.object(r.os, 'close'), patch.object(r.signal, 'pidfd_send_signal', side_effect=lambda *a: events.append('stop')), patch.object(r, 'wait_shell', side_effect=lambda *a: events.append('shell')), patch.object(r, 'command', side_effect=lambda *a: events.append(a[3])), patch.object(r, 'versions', return_value=version()), patch.object(r.ps, 'rc', side_effect=lambda *a: events.append('resume')), patch.object(r, 'verify_sessions', side_effect=lambda *a: events.append('verified')):
            r.execute({'entries': [e]})
        self.assertEqual(events, ['stop', 'shell', 'stop', 'update', 'start', 'resume', 'verified'])

    def test_partial_stop_retries_same_entries_without_duplicate_resume(self):
        e = entry()
        second = {**entry(), 'window': 8, 'pid': 21}
        j = {'desktop': 'desktop', 'entries': [e, second]}
        with patch.object(r, 'current_pid', side_effect=[20, 21, 20, 21]), patch.object(r, 'client_codex_pids', return_value={20, 21}), patch.object(r.os, 'pidfd_open', return_value=99), patch.object(r.os, 'close'), patch.object(r.signal, 'pidfd_send_signal'), patch.object(r, 'wait_shell', side_effect=[None, RuntimeError('still exiting')]), patch.object(r, 'command') as command, patch.object(r.ps, 'rc') as rc:
            with self.assertRaisesRegex(RuntimeError, 'still exiting'):
                r.execute(j)
        command.assert_not_called()
        rc.assert_not_called()
        saved = r.ps.read_json(r.JOURNAL)
        self.assertEqual(saved['entries'], [e, second])
        with patch.object(r, 'current_pid', return_value=None), patch.object(r, 'client_codex_pids', return_value=set()), patch.object(r, 'wait_shell'), patch.object(r, 'command'), patch.object(r, 'versions', return_value=version()), patch.object(r.ps, 'rc') as rc, patch.object(r, 'verify_sessions'):
            r.execute(saved)
        self.assertEqual(rc.call_count, 2)
        self.assertEqual(r.ps.read_json(r.JOURNAL)['entries'], [e, second])
        self.assertEqual(r.ps.read_json(r.JOURNAL)['phase'], 'complete')

    def test_restart_verification_requires_live_connection_not_startup_identity(self):
        w = {'pid': 10, 'foreground_processes': [{'pid': 20, 'cmdline': ['codex']}]}
        with patch.object(r, 'pane', return_value=w), patch.object(r.ps.codex_state, 'begin_capture'), patch.object(r.ps, 'codex_session', side_effect=r.ps.CodexSessionPending('still at startup menu')) as resolve, patch.object(r.time, 'monotonic', side_effect=[0, 0, 100]), patch.object(r.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Resume verification failed'):
                r.verify_sessions([entry()])
        resolve.assert_called_once_with(20, allow_startup=False)

    def test_concurrent_restart_rejected(self):
        import fcntl
        with (r.STATE / 'restart.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(r, 'capture') as capture, patch.object(r.ds, 'notify') as notify:
                r.run()
            capture.assert_not_called()
            self.assertIn('already running', notify.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
