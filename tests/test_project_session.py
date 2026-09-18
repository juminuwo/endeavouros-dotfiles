import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "config/bin/project-session"
loader = importlib.machinery.SourceFileLoader("project_session", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
ps = importlib.util.module_from_spec(spec)
loader.exec_module(ps)


def node(wid=10, mark="proj:alpha:claude", cls="kitty", workspace="7"):
    return {"type": "workspace", "name": workspace, "nodes": [
        {"window": wid, "id": wid + 100, "marks": [mark] if mark else [],
         "window_properties": {"class": cls}}]}


def kitty(wid=1):
    return {"id": 1, "platform_window_id": 10, "tabs": [{"id": 1, "windows": [
        {"id": wid, "cwd": "/tmp", "foreground_processes": []}]}]}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self.state_patch = patch.object(ps, "STATE", self.state)
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.desktop_patch = patch.object(ps, "desktop_id", return_value="desktop-1")
        self.desktop_patch.start()
        self.addCleanup(self.desktop_patch.stop)
        ps.atomic_json(self.state / "restore.json", {"desktop": "desktop-1", "complete": True})

    def snapshot(self, count=2):
        gen = "20260916T010000-abcdef01"
        folder = self.state / "snapshots" / gen
        folder.mkdir(parents=True)
        windows = []
        for i in range(count):
            (folder / f"{i}.kitty-session").write_text("new_tab test\nlaunch\n")
            windows.append({"file": f"{i}.kitty-session", "workspace": "7" if i == 0 else "_proj_beta_misc",
                            "marks": ["proj:alpha:claude" if i == 0 else "proj:beta:misc"], "panes": [], "tabs": 1})
        manifest = {"version": 1, "generation": gen, "windows": windows, "saved_at": "test"}
        ps.atomic_json(folder / "manifest.json", manifest)
        ps.atomic_json(self.state / "current.json", {"generation": gen})
        return folder, manifest

    def capture(self, root=None, rc=None):
        def default_rc(socket, *args):
            if args[0] == "ls":
                return json.dumps([kitty()])
            import shlex
            path = Path(shlex.split(args[1])[-1])
            path.write_text('new_tab test\nlayout splits\nlaunch \'kitty-unserialize-data={"id": 1}\' rm -rf /tmp/example\nfocus\nfocus_tab 0\n')
            return ""
        with patch.object(ps, "tree", return_value=root or node()), \
             patch.object(ps, "kitty_windows", return_value={10: ("socket", kitty())}), \
             patch.object(ps, "rc", side_effect=rc or default_rc), contextlib.redirect_stdout(io.StringIO()):
            ps.save()

    def test_native_launch_is_replaced_and_layout_preserved(self):
        sid = "01a07398-8416-7e63-9d79-403f86450217"
        native = '''os_window_class old-class
new_tab project
layout splits
set_layout_state {"tree": "native-layout"}
cd /stale
launch 'kitty-unserialize-data={"id": 1, "cmd_at_shell_startup": ["danger"]}' --env=TOKEN=secret --var=stale=1 sh -c 'danger'
focus
focus_tab 0
'''
        result = ps.safe_session(native, {1: {"cwd": "/a path/with 'quotes'", "codex": {"id": sid}}})
        self.assertIn('set_layout_state {"tree": "native-layout"}', result)
        self.assertIn(sid, result)
        self.assertIn("--session", result)
        for unwanted in ["danger", "secret", "stale", "old-class", "cmd_at_shell_startup"]:
            self.assertNotIn(unwanted, result)

    def test_missing_pane_rejects_partial_serialization(self):
        with self.assertRaisesRegex(RuntimeError, "panes changed"):
            ps.safe_session("new_tab test\n", {1: {"cwd": "/tmp"}})

    def test_starting_resume_cannot_be_saved_as_an_empty_shell(self):
        window = {"cwd": "/repo", "foreground_processes": [
            {"pid": 123, "cmdline": ["python3", "/home/user/.local/bin/project-session", "pane", "--session", "saved-id"]}]}
        with self.assertRaisesRegex(RuntimeError, "still starting"):
            ps.pane_info(window)

    def test_success_publishes_complete_safe_snapshot(self):
        self.capture()
        folder, manifest = ps.snapshot()
        self.assertEqual(manifest["windows"][0]["marks"], ["proj:alpha:claude"])
        self.assertIn("project-session pane", (folder / "0.kitty-session").read_text())
        self.assertNotIn("rm -rf", (folder / "0.kitty-session").read_text())
        self.assertFalse((folder / "native.tmp").exists())

    def test_failed_capture_preserves_previous_generation(self):
        folder, _ = self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.capture(rc=lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("kitten", 15)))
        self.assertEqual(pointer, (self.state / "current.json").read_bytes())
        self.assertEqual(list((self.state / "snapshots").iterdir()), [folder])

    def test_pending_conversation_preserves_snapshot_during_either_capture_pass(self):
        folder, _ = self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        for results in ([ps.CodexSessionPending('pending')],
                        [{"cwd": "/tmp"}, ps.CodexSessionPending('pending')]):
            with patch.object(ps, 'pane_info', side_effect=results):
                with self.assertRaises(ps.CodexSessionPending):
                    self.capture()
            self.assertEqual(pointer, (self.state / "current.json").read_bytes())
            self.assertEqual(list((self.state / "snapshots").iterdir()), [folder])

    def test_no_projects_preserves_previous_generation(self):
        self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "No project windows"):
            self.capture(root={"nodes": []})
        self.assertEqual(pointer, (self.state / "current.json").read_bytes())

    def test_coordinator_rejects_project_disappearance_before_capture(self):
        self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        with patch.object(ps, "tree", return_value=node()):
            with self.assertRaisesRegex(RuntimeError, "changed before capture"):
                ps.save(expected_windows=[])
        self.assertEqual(pointer, (self.state / "current.json").read_bytes())

    def test_anchorless_survivors_keep_hidden_and_active_identity(self):
        root = {"nodes": [node(), node(20, "", workspace="6"), node(30, "", workspace="_proj_beta_misc")]}
        found = ps.project_windows(root)
        self.assertEqual([n["marks"] for ws, n in found],
                         [["proj:alpha:claude"], ["proj:alpha:misc"], ["proj:beta:misc"]])
        self.assertEqual(root["nodes"][1]["nodes"][0]["marks"], [])

    def test_misplaced_project_does_not_publish_unrestorable_generation(self):
        self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "outside its workspace"):
            self.capture(root=node(workspace="8"))
        self.assertEqual(pointer, (self.state / "current.json").read_bytes())

    def test_active_identity_loss_cannot_silently_omit_survivor(self):
        with self.assertRaisesRegex(RuntimeError, "no active project identity"):
            ps.project_windows(node(mark=""))

    def test_save_blocked_until_restore_complete(self):
        self.snapshot()
        ps.atomic_json(self.state / "restore.json", {"desktop": "desktop-1", "complete": False})
        with patch.object(ps, "tree") as tree:
            ps.save(auto=True)
            tree.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "not complete"):
                ps.save()

    def test_kitty_topology_change_does_not_commit(self):
        self.snapshot()
        pointer = (self.state / "current.json").read_bytes()
        def changing(socket, *args):
            import shlex
            if args[0] == "ls":
                return json.dumps([kitty(wid=2)])
            Path(shlex.split(args[1])[-1]).write_text('launch \'kitty-unserialize-data={"id": 1}\'\n')
            return ""
        with self.assertRaisesRegex(RuntimeError, "tabs changed"):
            self.capture(rc=changing)
        self.assertEqual(pointer, (self.state / "current.json").read_bytes())

    def test_empty_new_desktop_cannot_overwrite_snapshot_before_startup(self):
        self.snapshot()
        with patch.object(ps, "desktop_id", return_value="desktop-2"), patch.object(ps, "tree") as tree:
            ps.save(auto=True)
            tree.assert_not_called()

    def test_live_or_initialized_workspace_is_not_restored(self):
        self.snapshot()
        with patch.object(ps.subprocess, "Popen") as spawn, contextlib.redirect_stdout(io.StringIO()):
            ps.restore()
            spawn.assert_not_called()
            with patch.object(ps, "desktop_id", return_value="desktop-2"), patch.object(ps, "tree", return_value=node()):
                ps.restore()
            spawn.assert_not_called()

    def test_interrupted_restore_reuses_spawn_before_mark_and_retries_missing(self):
        _, manifest = self.snapshot()
        (self.state / "restore.json").unlink()
        roots = []
        spawned = []
        def root():
            return {"nodes": roots}
        def spawn(args, **kwargs):
            cls = args[args.index("--class") + 1]
            spawned.append(cls)
            roots.append(node(len(roots) + 1, "", cls, "1"))
        fail_once = [True]
        def command(cmd):
            if fail_once[0]:
                fail_once[0] = False
                raise RuntimeError("i3 unavailable after spawn")
            import re
            con = int(re.search(r"con_id=(\d+)", cmd)[1])
            for ws in roots:
                n = ws["nodes"][0]
                if n["id"] != con:
                    continue
                if "move container" in cmd:
                    ws["name"] = json.loads(cmd.split("workspace ", 1)[1].split(", floating", 1)[0])
                if "mark --add" in cmd:
                    n["marks"].append(json.loads(cmd.split("mark --add ", 1)[1]))
        with patch.object(ps, "tree", side_effect=root), patch.object(ps, "i3", side_effect=command), \
             patch.object(ps.subprocess, "Popen", side_effect=spawn), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "after spawn"):
                ps.restore()
            self.assertFalse(ps.read_json(self.state / "restore.json")["complete"])
            ps.restore()
        self.assertEqual(len(spawned), 2)
        self.assertEqual([w["name"] for w in roots], [w["workspace"] for w in manifest["windows"]])
        self.assertEqual([w["nodes"][0]["marks"] for w in roots], [w["marks"] for w in manifest["windows"]])

    def test_i3_rejection_is_an_error(self):
        with patch.object(ps, "run", return_value='[{"success": false, "error": "no window"}]'):
            with self.assertRaisesRegex(RuntimeError, "i3 rejected"):
                ps.i3("move")

    def test_restored_codex_uses_neovim_despite_display_manager_environment(self):
        args = SimpleNamespace(cwd=self.tmp.name, codex_home=None,
                               session='saved-conversation', dashboard=False)
        observed = {}
        def launch(argv, **kwargs):
            observed.update(argv=argv, editor=os.environ.get('EDITOR'), visual=os.environ.get('VISUAL'))
        with patch.dict(os.environ, {'EDITOR': 'nano', 'VISUAL': 'nano'}), \
             patch.object(ps.os, 'chdir'), patch.object(ps.signal, 'signal'), \
             patch.object(ps.subprocess, 'run', side_effect=launch), patch.object(ps.os, 'execl'):
            ps.pane(args)
        self.assertEqual(observed['editor'], 'nvim')
        self.assertEqual(observed['visual'], 'nvim')
        self.assertEqual(observed['argv'], ['codex', 'resume', args.session, '--cd', self.tmp.name])

    def test_direct_helper_serializes_with_project_switch_lock(self):
        # Use the real shared flock without touching live workspace state.
        with open(ps.LOCK, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            env = dict(os.environ, XDG_STATE_HOME=str(Path(self.tmp.name) / "isolated"))
            env.pop("PROJECT_SWITCH_LOCK_FD", None)
            process = subprocess.Popen([str(SCRIPT), "status"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    process.communicate(timeout=0.15)
                fcntl.flock(lock, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn(b"No project workspace saved", stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_codex_ignores_subagents_and_rejects_multiple_main_threads(self):
        sid = "01a07398-8416-7e63-9d79-403f86450217"
        root = Path(self.tmp.name) / "rollout-main.jsonl"
        sub = Path(self.tmp.name) / "rollout-sub.jsonl"
        root.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": "/repo", "source": "cli"}}))
        sub.write_text(json.dumps({"type": "session_meta", "payload": {"id": "01a073ba-4300-7ae0-9c41-77ccaebc9374", "cwd": "/repo", "source": {"subagent": {}}}}))
        with patch.object(Path, "iterdir", return_value=iter([sub, root])), patch.object(Path, "read_bytes", return_value=b"CODEX_HOME=/custom\0TOKEN=secret\0"):
            result = ps.codex_session(123)
        self.assertEqual(result, {"id": sid, "cwd": "/repo", "home": "/custom"})
        other = Path(self.tmp.name) / "rollout-other.jsonl"
        other.write_text(root.read_text().replace(sid, "01a073ba-4300-7ae0-9c41-77ccaebc9374"))
        with patch.object(Path, "iterdir", return_value=iter([root, other])):
            with self.assertRaisesRegex(RuntimeError, "Cannot identify one main") as raised:
                ps.codex_session(123)
            self.assertNotIsInstance(raised.exception, ps.CodexSessionPending)

    def test_codex_without_rollout_is_pending_but_corrupt_rollout_is_error(self):
        with patch.object(Path, 'iterdir', return_value=iter([])):
            with self.assertRaises(ps.CodexSessionPending):
                ps.codex_session(123)
        bad = Path(self.tmp.name) / 'rollout-bad.jsonl'
        bad.write_text('invalid json')
        with patch.object(Path, 'iterdir', return_value=iter([bad])):
            with self.assertRaises(RuntimeError) as raised:
                ps.codex_session(123)
            self.assertNotIsInstance(raised.exception, ps.CodexSessionPending)


if __name__ == "__main__":
    unittest.main()
