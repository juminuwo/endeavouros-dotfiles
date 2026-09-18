import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'config/bin/desktop-session'
loader = importlib.machinery.SourceFileLoader('desktop_session', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
ds = importlib.util.module_from_spec(spec)
loader.exec_module(ds)
REAL_NOTIFY = ds.notify


def desktop():
    return {'nodes': [
        {'type': 'workspace', 'name': name, 'layout': 'splith', 'nodes': [
            {'window': index + 1, 'id': index + 101, 'window_properties': {'class': 'App', 'instance': name}}]}
        for index, name in enumerate(['1: browser', '6', '7', '_proj_work_misc', '8'])]}


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'state'
        self.state.mkdir()
        for name, value in [('STATE', self.state)]:
            p = patch.object(ds, name, value); p.start(); self.addCleanup(p.stop)
        for name, value in [('desktop_id', 'desktop-1'), ('tree', desktop())]:
            p = patch.object(ds.ps, name, return_value=value); p.start(); self.addCleanup(p.stop)
        p = patch.object(ds, 'notify'); self.notify = p.start(); self.addCleanup(p.stop)
        ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': True})

    def capture(self, fail=False, **save_options):
        def command(*args, **kwargs):
            if fail:
                raise RuntimeError('application capture failed')
            name = args[args.index('-w') + 1]
            profile = args[args.index('-p') + 1]
            folder = Path(args[args.index('-d') + 1]) / 'profiles'
            folder.mkdir(exist_ok=True)
            layout = {'nodes': [{'swallows': [{'class': '^App$', 'instance': '^' + name + '$'}]}]}
            ds.ps.atomic_json(folder / f'{profile}_layout.json', layout)
            ds.ps.atomic_json(folder / f'{profile}_programs.json', [{'command': ['app'], 'working_directory': '/tmp'}])
        with patch.object(ds, 'command', side_effect=command), patch.object(ds.ps, 'save') as project_save, \
             patch.object(ds.ps, 'snapshot', return_value=(None, {})), patch.object(ds.ps, 'summary', return_value='4 projects, 7 Codex conversations'), \
             contextlib.redirect_stdout(io.StringIO()):
            ds.save(**save_options)
        return project_save.call_count

    def test_enumerates_renamed_workspaces_and_excludes_projects(self):
        self.assertEqual([w['name'] for w in ds.ordinary(desktop())], ['1: browser', '8'])

    def test_success_has_one_notification_after_complete_publication(self):
        self.capture()
        folder, manifest = ds.pointer()
        self.assertEqual(manifest['windows'], 2)
        self.assertEqual([w['name'] for w in manifest['workspaces']], ['1: browser', '8'])
        self.assertTrue((folder / '0.layout.json').is_file())
        self.notify.assert_called_once()
        self.assertIn('2 application windows', self.notify.call_args.args[1])
        self.assertTrue(ds.ps.read_json(self.state / 'last-save.json')['ok'])

    def test_failure_preserves_published_generation_and_no_success_notification(self):
        self.capture()
        original = (self.state / 'current.json').read_bytes()
        self.notify.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'capture failed'):
            self.capture(fail=True)
        self.assertEqual(original, (self.state / 'current.json').read_bytes())
        self.notify.assert_not_called()
        self.assertEqual(len(list((self.state / 'snapshots').iterdir())), 1)

    def test_autosave_skips_incomplete_boot_and_shutdown(self):
        with patch.object(ds.ps, 'save') as projects:
            ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': False})
            ds.save(auto=True)
            projects.assert_not_called()
            ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': True})
            ds.ps.atomic_json(self.state / 'shutdown.json', {'desktop': 'desktop-1'})
            ds.save(auto=True)
            projects.assert_not_called()

    def test_empty_desktop_cannot_erase_snapshot(self):
        self.capture()
        original = (self.state / 'current.json').read_bytes()
        with patch.object(ds.ps, 'tree', return_value={'nodes': []}):
            with self.assertRaisesRegex(RuntimeError, 'empty'):
                ds.save()
        self.assertEqual(original, (self.state / 'current.json').read_bytes())

    def test_project_autosave_keeps_desktop_snapshot_and_clears_stale_failure(self):
        self.capture()
        original = (self.state / 'current.json').read_bytes()
        ds.ps.atomic_json(self.state / 'last-save.json', {'ok': False, 'message': 'old failure'})
        self.notify.reset_mock()
        manifest = {'saved_at': 'now', 'windows': []}
        with patch.object(ds.ps, 'save', return_value=manifest) as projects, patch.object(ds, 'command') as command:
            ds.save(auto=True, projects_only=True)
        projects.assert_called_once_with(auto=True)
        command.assert_not_called()
        self.notify.assert_not_called()
        self.assertEqual((self.state / 'current.json').read_bytes(), original)
        self.assertTrue(ds.ps.read_json(self.state / 'last-save.json')['ok'])
        with contextlib.redirect_stdout(io.StringIO()):
            status = ds.status()
        self.assertNotIn('FAILED', status)
        self.assertIn('Last project save: Saved now', status)

    def test_skipped_project_save_does_not_clear_failure(self):
        last = {'ok': False, 'message': 'previous failure'}
        ds.ps.atomic_json(self.state / 'last-save.json', last)
        with patch.object(ds.ps, 'save', return_value=None):
            ds.save(auto=True, projects_only=True)
        self.assertEqual(ds.ps.read_json(self.state / 'last-save.json'), last)

    def test_pending_autosave_is_deferred_but_manual_and_shutdown_saves_fail(self):
        self.capture()
        original = (self.state / 'current.json').read_bytes()
        for options in (['--auto', '--projects-only'], ['--projects-only'], [],
                        ['--auto', '--shutdown'], ['--auto', '--projects-only', '--shutdown']):
            self.notify.reset_mock()
            with patch.object(sys, 'argv', [str(SCRIPT), 'save', *options]), \
                 patch.object(ds, 'save', side_effect=ds.ps.CodexSessionPending('pending')), \
                 contextlib.redirect_stdout(io.StringIO()):
                if options == ['--auto', '--projects-only']:
                    ds.main()
                    self.notify.assert_not_called()
                    record = ds.ps.read_json(self.state / 'last-save.json')
                    self.assertTrue(record['deferred'])
                    self.assertFalse(record['ok'])
                    self.assertIn('autosave deferred', ds.status())
                else:
                    with self.assertRaises(ds.ps.CodexSessionPending):
                        ds.main()
                    self.notify.assert_called_once()
                    self.assertFalse(ds.ps.read_json(self.state / 'last-save.json')['ok'])
            self.assertEqual((self.state / 'current.json').read_bytes(), original)

    def test_real_autosave_error_remains_failure(self):
        with patch.object(sys, 'argv', [str(SCRIPT), 'save', '--auto', '--projects-only']), \
             patch.object(ds, 'save', side_effect=RuntimeError('ambiguous conversation')):
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                ds.main()
        self.assertFalse(ds.ps.read_json(self.state / 'last-save.json')['ok'])
        self.notify.assert_called_once()

    def test_project_autosave_skips_incomplete_restore_and_shutdown(self):
        with patch.object(ds.ps, 'save') as projects:
            ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': False})
            ds.save(auto=True, projects_only=True)
            ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': True})
            ds.ps.atomic_json(self.state / 'shutdown.json', {'desktop': 'desktop-1'})
            ds.save(auto=True, projects_only=True)
        projects.assert_not_called()

    def test_power_actions_still_request_full_desktop_save(self):
        for action in ['shutdown', 'reboot', 'logout']:
            with self.subTest(action=action), patch.object(ds, 'save') as save, \
                 patch.object(ds, 'command'), patch.object(ds.ps, 'i3'):
                ds.power(action)
                save.assert_called_once_with()

    def test_power_actions_never_execute_after_save_failure(self):
        for action in ['shutdown', 'reboot', 'logout']:
            with self.subTest(action=action), patch.object(ds, 'save', side_effect=RuntimeError('save failed')), \
                 patch.object(ds, 'command') as command, patch.object(ds.ps, 'i3') as i3:
                with self.assertRaisesRegex(RuntimeError, 'save failed'):
                    ds.power(action)
                command.assert_not_called()
                i3.assert_not_called()

    def test_failed_power_request_unfreezes_future_saves(self):
        with patch.object(ds, 'save'), patch.object(ds, 'command', side_effect=RuntimeError('reboot denied')):
            with self.assertRaisesRegex(RuntimeError, 'denied'):
                ds.power('reboot')
        self.assertFalse((self.state / 'shutdown.json').exists())

    def test_repeated_startup_does_not_relaunch_or_append_layout(self):
        with patch.object(ds, 'command'), patch.object(ds, 'start_app') as spawn, \
             patch.object(ds.ps, 'i3') as i3, contextlib.redirect_stdout(io.StringIO()):
            ds.restore()
        spawn.assert_not_called()
        i3.assert_not_called()

    def test_fresh_install_initializes_without_old_legacy_profiles(self):
        (self.state / 'restore.json').unlink()
        with patch.object(ds, 'command') as command, contextlib.redirect_stdout(io.StringIO()):
            ds.restore()
        command.assert_called_once()
        self.assertTrue(ds.ps.read_json(self.state / 'restore.json')['complete'])

    def test_placeholder_is_not_a_verified_application(self):
        root = {'type': 'workspace', 'name': '1', 'nodes': [
            {'window': 20, 'marks': ['token'], 'window_properties': {'transient_for': None}}]}
        with patch.object(ds.ps, 'tree', return_value=root):
            self.assertIsNone(ds.filled({'token': 'token'}))

    def test_obsidian_identity_aliases_are_exact_and_bidirectional(self):
        old = {'class': 'obsidian', 'instance': 'obsidian'}
        new = {'class': 'md.obsidian.Obsidian', 'instance': 'md.obsidian.obsidian'}
        self.assertTrue(ds.matching(new, {'properties': old}))
        self.assertTrue(ds.matching(old, {'properties': new}))
        self.assertFalse(ds.matching({'class': new['class'], 'instance': 'unrelated'}, {'properties': old}))
        self.assertFalse(ds.matching({'class': 'OtherApp', 'instance': 'obsidian'}, {'properties': old}))

    def test_new_obsidian_class_uses_stable_launcher(self):
        with patch.object(ds.shutil, 'which', return_value='/usr/bin/obsidian'):
            self.assertEqual(ds.app_command(['/usr/lib/electron43/electron', '/usr/lib/obsidian/app.asar'],
                                           {'class': 'md.obsidian.Obsidian'}), ['obsidian'])

    def test_obsidian_layout_accepts_both_versions_without_changing_snapshot(self):
        app = {'token': 'saved', 'properties': {'class': 'obsidian', 'instance': 'obsidian'}}
        layout = [{'marks': ['saved'], 'swallows': [{'class': '^obsidian$', 'instance': '^obsidian$', 'window_role': '^browser-window$'}]}]
        upgraded = ds.compatible_layout(layout, [app])
        for cls, instance in ds.OBSIDIAN_IDENTITIES:
            self.assertTrue(any(re.fullmatch(c['class'], cls) and
                                re.fullmatch(c['instance'], instance)
                                for c in upgraded[0]['swallows']))
        self.assertEqual(len(layout[0]['swallows']), 1)
        self.assertTrue(all(c['window_role'] == '^browser-window$' for c in upgraded[0]['swallows']))
        self.assertEqual(ds.compatible_layout(layout, []), layout)

    def test_retry_skips_completed_apps_and_existing_layouts(self):
        self.capture()
        folder, manifest = ds.pointer()
        apps = [a for ws in manifest['workspaces'] for a in ws['apps']]
        ds.ps.atomic_json(self.state / 'restore.json', {'desktop': 'desktop-1', 'complete': False,
            'generation': manifest['generation'], 'layouts': [0, 1], 'done': [apps[0]['token']]})
        with patch.object(ds, 'command'), patch.object(ds, 'adopt_existing', return_value=True) as adopt, \
             patch.object(ds.ps, 'i3') as i3, patch.object(ds, 'start_app') as launch, contextlib.redirect_stdout(io.StringIO()):
            ds.restore()
        adopt.assert_called_once_with(apps[1])
        launch.assert_not_called()
        i3.assert_not_called()
        self.assertTrue(ds.ps.read_json(self.state / 'restore.json')['complete'])

    def test_status_does_not_hide_last_failed_save(self):
        self.capture()
        ds.ps.atomic_json(self.state / 'last-save.json', {'ok': False, 'message': 'Kitty unavailable'})
        with contextlib.redirect_stdout(io.StringIO()):
            result = ds.status()
        self.assertIn('Last save FAILED: Kitty unavailable', result)
        self.assertIn('2 application windows', result)

    def test_notification_failure_cannot_turn_committed_save_into_failure(self):
        with patch.object(ds, 'notify', REAL_NOTIFY), patch.object(ds.shutil, 'which', return_value='/usr/bin/notify-send'), \
             patch.object(ds.subprocess, 'run', side_effect=subprocess.TimeoutExpired('notify-send', 3)), \
             contextlib.redirect_stderr(io.StringIO()):
            self.capture()
        self.assertTrue(ds.ps.read_json(self.state / 'last-save.json')['ok'])
        self.assertIsNotNone(ds.pointer()[1])

    def test_no_open_projects_keeps_previous_project_snapshot_and_saves_desktop(self):
        self.assertEqual(self.capture(), 0)
        self.assertIn('unchanged; no open project windows', ds.pointer()[1]['projects'])

    def test_shutdown_allows_apps_closed_since_old_manual_snapshot(self):
        self.capture()
        shrunk = desktop()
        shrunk['nodes'].pop()
        with patch.object(ds.ps, 'tree', return_value=shrunk):
            self.capture(shutdown=True)
        self.assertEqual(ds.pointer()[1]['windows'], 1)

    def test_shutdown_rejects_windows_closing_during_capture(self):
        self.capture()
        previous = (self.state / 'current.json').read_bytes()
        shrunk = desktop()
        shrunk['nodes'].pop()
        with patch.object(ds.ps, 'tree', side_effect=[desktop(), shrunk]):
            with self.assertRaisesRegex(RuntimeError, 'windows changed during capture'):
                self.capture(shutdown=True)
        self.assertEqual(previous, (self.state / 'current.json').read_bytes())

    def test_listener_is_initialized_before_a_restore_that_fails(self):
        events = []
        def fail():
            events.append('restore')
            raise RuntimeError('missing application')
        with patch.object(sys, 'argv', [str(SCRIPT), 'startup']), \
             patch.object(ds, 'command', side_effect=lambda *args: events.append(args)), patch.object(ds, 'restore', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'missing application'):
                ds.main()
        self.assertIn('import-environment', events[0])
        self.assertIn('desktop-session-shutdown.service', events[1])
        self.assertEqual(events[2], 'restore')

    def test_shutdown_timeout_releases_inhibitor_and_preserves_snapshot(self):
        self.capture()
        original = (self.state / 'current.json').read_bytes()
        callbacks = []
        fd = os.open('/dev/null', os.O_RDONLY)
        manager = SimpleNamespace(Inhibit=lambda *args: SimpleNamespace(take=lambda: fd))
        props = SimpleNamespace(Get=lambda *args: 5000000)
        bus = SimpleNamespace(get_object=lambda *args: object(),
                              add_signal_receiver=lambda callback, **kwargs: callbacks.append(callback))
        fake_dbus = SimpleNamespace(SystemBus=lambda: bus, Interface=lambda obj, name: props if name.endswith('Properties') else manager)
        modules = {'dbus': fake_dbus, 'dbus.mainloop': SimpleNamespace(),
                   'dbus.mainloop.glib': SimpleNamespace(DBusGMainLoop=lambda **kwargs: None),
                   'gi': SimpleNamespace(), 'gi.repository': SimpleNamespace(GLib=SimpleNamespace(
                       MainLoop=lambda: SimpleNamespace(run=lambda: callbacks[0](True))))}
        with patch.dict(sys.modules, modules), patch.object(ds.subprocess, 'run', side_effect=subprocess.TimeoutExpired('save', 4.5)) as save, \
             contextlib.redirect_stdout(io.StringIO()):
            ds.watch_shutdown()
        self.assertEqual(save.call_args.kwargs['timeout'], 4.5)
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.assertEqual(original, (self.state / 'current.json').read_bytes())
        self.assertEqual(ds.ps.read_json(self.state / 'shutdown.json')['desktop'], 'desktop-1')


if __name__ == '__main__':
    unittest.main()
