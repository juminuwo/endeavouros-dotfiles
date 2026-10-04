import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('codex_state', Path(__file__).resolve().parents[1] / 'config/bin/codex-session-state.py')
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)
SID = '01a08243-3ba4-70c1-a611-4d9470093d6a'
OTHER = '01a0a426-7cc7-72b0-8916-a0c19bae5b39'


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        cs.begin_capture()
        self.addCleanup(cs.begin_capture)
        self.home = Path('/custom/codex')
        self.session = {'id': SID, 'cwd': '/same/repo'}
        self.roots = [('http://127.0.0.1:1234', 'connected', self.session),
                      ('http://127.0.0.1:5678', 'connected', {'id': OTHER, 'cwd': '/same/repo'})]
        for target, kwargs in [
                (cs, {'process_identity': lambda pid: str(pid)}),
                (cs, {'listener_origins': lambda pid: {f'http://127.0.0.1:{pid}'}})]:
            for name, value in kwargs.items():
                p = patch.object(target, name, side_effect=value)
                p.start(); self.addCleanup(p.stop)
        p = patch.object(Path, 'exists', return_value=True)
        p.start(); self.addCleanup(p.stop)

    def test_same_cwd_two_terminals_and_home(self):
        with patch.object(cs, 'daemon_roots', return_value=self.roots) as lookup:
            self.assertEqual(cs.resolve(1234, self.home), self.session)
            self.assertEqual(cs.resolve(5678, self.home)['id'], OTHER)
            lookup.assert_called_once_with(self.home)
            cs.verify_capture()
            self.assertEqual(lookup.call_count, 2)

    def test_ambiguous_old_and_new_root_fails_without_guessing(self):
        roots = self.roots + [('http://127.0.0.1:1234', 'connected', {'id': OTHER, 'cwd': '/elsewhere'})]
        with patch.object(cs, 'daemon_roots', return_value=roots):
            with self.assertRaisesRegex(RuntimeError, 'one connected'):
                cs.resolve(1234, self.home)

    def test_switch_disconnection_or_pid_reuse_rejected_at_publication(self):
        for change in ['switch', 'disconnect', 'pid', 'listener']:
            with self.subTest(change=change):
                cs.begin_capture()
                with patch.object(cs, 'daemon_roots', return_value=self.roots):
                    cs.resolve(1234, self.home)
                fresh = [('http://127.0.0.1:1234', 'connected', {'id': OTHER, 'cwd': '/same/repo'})] if change == 'switch' else self.roots
                if change == 'disconnect': fresh = []
                with patch.object(cs, 'daemon_roots', return_value=fresh), \
                     patch.object(cs, 'process_identity', return_value='reused' if change == 'pid' else '1234'), \
                     patch.object(cs, 'listener_origins', return_value=set() if change == 'listener' else {'http://127.0.0.1:1234'}):
                    with self.assertRaisesRegex(RuntimeError, 'changed'):
                        cs.verify_capture()

    def test_infrastructure_failure_and_missing_mapping_are_errors(self):
        with patch.object(cs, 'daemon_roots', side_effect=TimeoutError('timeout')):
            with self.assertRaises(TimeoutError): cs.resolve(1234, self.home)
        with patch.object(cs, 'daemon_roots', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'one connected'): cs.resolve(1234, self.home)
        with patch.object(cs, 'listener_origins', return_value=set()):
            self.assertIsNone(cs.resolve(1234, self.home))

    def test_thread_metadata_excludes_subagents_but_accepts_resumed_vscode(self):
        class FakeRpc:
            def __init__(self, path): pass
            def pages(self, method, params):
                if method == 'thread/loaded/list': return [SID, OTHER, 'child']
                return [{'name': 'codex_tui', 'httpOrigin': 'http://127.0.0.1:1234', 'runtimeStatus': 'connected'}]
            def call(self, method, params):
                sid = params['threadId']
                return {'thread': {'id': sid, 'cwd': '/repo', 'source': 'vscode',
                                   'parentThreadId': SID if sid == 'child' else None}}
            def close(self): pass
        with patch.object(cs, 'Rpc', FakeRpc), patch.object(cs, 'persisted', return_value=True):
            self.assertEqual([r[2]['id'] for r in cs.daemon_roots(self.home)], [SID, OTHER])

    def test_unfiltered_daemon_response_is_rejected(self):
        from unittest.mock import Mock
        rpc = Mock()
        rpc.pages.side_effect = [[SID], [{'name': 'linear', 'httpOrigin': 'https://mcp.linear.app'}]]
        rpc.call.return_value = {'thread': {'id': SID, 'cwd': '/repo', 'source': 'cli'}}
        with patch.object(cs, 'Rpc', return_value=rpc), patch.object(cs, 'persisted', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'ignored the local-only MCP filter'):
                cs.daemon_roots(self.home)
        rpc.close.assert_called_once()

    def test_persistence_requires_matching_saved_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'rollout.jsonl'
            thread = {'id': SID, 'path': str(path)}
            self.assertFalse(cs.persisted(thread))
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': SID}}))
            self.assertTrue(cs.persisted(thread))
            self.assertFalse(cs.persisted({**thread, 'ephemeral': True}))
            self.assertFalse(cs.persisted({**thread, 'id': OTHER}))
            path.write_text('corrupt')
            self.assertFalse(cs.persisted(thread))

    def test_unrelated_unrestorable_conversation_does_not_block_save(self):
        roots = [self.roots[0], (self.roots[1][0], 'unrestorable', self.roots[1][2])]
        with patch.object(cs, 'daemon_roots', return_value=roots):
            self.assertEqual(cs.resolve(1234, self.home), self.session)
            with self.assertRaisesRegex(RuntimeError, 'saved Codex'):
                cs.resolve(5678, self.home)


    def test_only_authoritatively_unused_startup_thread_is_excluded(self):
        from unittest.mock import Mock
        thread = {'id': SID, 'status': {'type': 'idle'}, 'name': None, 'preview': '', 'path': None}
        error = cs.RpcError('thread/turns/list', {'code': -32600, 'message':
            f'thread {SID} is not materialized yet; thread/turns/list is unavailable before first user message'})
        rpc = Mock()
        rpc.call.side_effect = error
        self.assertTrue(cs.unused_startup_thread(rpc, thread))
        for changed in [{'ephemeral': True}, {'preview': 'real user message'},
                        {'name': 'named task'}, {'status': {'type': 'active'}},
                        {'path': '/existing/corrupt/rollout'}]:
            with self.subTest(changed=changed):
                rpc.reset_mock()
                self.assertFalse(cs.unused_startup_thread(rpc, {**thread, **changed}))
                rpc.call.assert_not_called()
        rpc.call.side_effect = cs.RpcError('thread/turns/list', {'code': -32600, 'message': 'other failure'})
        with self.assertRaises(cs.RpcError): cs.unused_startup_thread(rpc, thread)
        rpc.call.side_effect = TimeoutError('timeout')
        with self.assertRaises(TimeoutError): cs.unused_startup_thread(rpc, thread)
        rpc.call.side_effect = None
        rpc.call.return_value = {'data': [], 'nextCursor': None}
        self.assertFalse(cs.unused_startup_thread(rpc, thread))

    def test_saved_root_and_confirmed_startup_blank_on_same_terminal_succeed(self):
        class FakeRpc:
            def __init__(self, path): pass
            def pages(self, method, params):
                if method == 'thread/loaded/list': return [SID, OTHER]
                return [{'name': 'codex_tui', 'httpOrigin': 'http://127.0.0.1:1234', 'runtimeStatus': 'connected'}]
            def call(self, method, params):
                sid = params['threadId']
                if method == 'thread/turns/list':
                    raise cs.RpcError(method, {'code': -32600, 'message':
                        f'thread {sid} is not materialized yet; thread/turns/list is unavailable before first user message'})
                return {'thread': {'id': sid, 'cwd': '/same/repo', 'source': 'vscode',
                    'parentThreadId': None, 'ephemeral': False, 'preview': '', 'name': None,
                    'status': {'type': 'idle'}, 'path': None}}
            def close(self): pass
        with patch.object(cs, 'Rpc', FakeRpc), \
             patch.object(cs, 'persisted', side_effect=lambda t: t['id'] == SID):
            self.assertEqual(cs.resolve(1234, self.home), self.session)
            cs.verify_capture()

    def test_startup_blank_materializing_during_capture_rejects_save(self):
        with patch.object(cs, 'daemon_roots', return_value=[self.roots[0]]):
            cs.resolve(1234, self.home)
        materialized = self.roots[0], ('http://127.0.0.1:1234', 'connected', {'id': OTHER, 'cwd': '/repo'})
        with patch.object(cs, 'daemon_roots', return_value=materialized):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                cs.verify_capture()


class TransportTests(unittest.TestCase):
    def rpc_stub(self, version='0.160.0'):
        from unittest.mock import Mock
        rpc = cs.Rpc.__new__(cs.Rpc)
        rpc.server_version = version
        rpc.sequence = 0
        rpc.send = Mock()
        rpc.receive = Mock(return_value={'id': 1, 'result': {'data': [], 'nextCursor': None}})
        return rpc

    def test_old_or_unknown_daemon_cannot_probe_remote_servers(self):
        for version in ['0.157.1', '0.159.0', 'unknown']:
            with self.subTest(version=version):
                rpc = self.rpc_stub(version)
                with self.assertRaisesRegex(RuntimeError, 'update the pinned daemon'):
                    rpc.call('mcpServerStatus/list', {'threadId': SID, 'serverName': 'codex_tui'})
                rpc.send.assert_not_called()
                rpc.receive.assert_not_called()

    def test_status_requests_must_be_scoped_to_local_terminal(self):
        for params in [{}, {'threadId': SID}, {'serverName': 'codex_tui'},
                       {'threadId': SID, 'serverName': 'linear'}]:
            rpc = self.rpc_stub()
            with self.assertRaisesRegex(RuntimeError, 'thread-scoped'):
                rpc.call('mcpServerStatus/list', params)
            rpc.send.assert_not_called()
        rpc = self.rpc_stub()
        rpc.call('mcpServerStatus/list', {'threadId': SID, 'serverName': 'codex_tui', 'detail': 'toolsAndAuthOnly'})
        request = json.loads(rpc.send.call_args.args[0])
        self.assertEqual(request['params']['serverName'], 'codex_tui')
        self.assertEqual(request['params']['threadId'], SID)

    def test_timeout_reports_method_and_thread_for_reads_and_writes(self):
        for target in ['send', 'receive']:
            rpc = self.rpc_stub()
            getattr(rpc, target).side_effect = TimeoutError('timed out')
            with self.assertRaisesRegex(RuntimeError, f'Codex thread/read .*{SID}.*timed out'):
                rpc.call('thread/read', {'threadId': SID})

    def test_unix_handshake_masking_fragmentation_and_ping(self):
        import base64
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'rpc.sock')
            server = socket.socket(socket.AF_UNIX)
            self.addCleanup(server.close)
            server.bind(path); server.listen()
            failures = []
            def serve():
                try:
                    conn, _ = server.accept()
                    with conn, conn.makefile('rb') as stream:
                        conn.settimeout(3)
                        headers = {}
                        while True:
                            line = stream.readline()
                            if line == b'\r\n': break
                            if b':' in line:
                                k, v = line.decode().split(':', 1); headers[k.lower()] = v.strip()
                        accept = base64.b64encode(hashlib.sha1((headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
                        conn.sendall(b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
                        def receive():
                            first, second = stream.read(2)
                            self.assertTrue(second & 128)
                            size = second & 127
                            if size == 126: size = struct.unpack('!H', stream.read(2))[0]
                            mask = stream.read(4); data = stream.read(size)
                            return first & 15, bytes(v ^ mask[i % 4] for i, v in enumerate(data))
                        _, init = receive()
                        self.assertEqual(json.loads(init)['method'], 'initialize')
                        conn.sendall(b'\x89\x01x')
                        self.assertEqual(receive(), (10, b'x'))
                        tail = b'"result":{"userAgent":"codex-tui/0.160.0 (test)"}}'
                        conn.sendall(b'\x01\x08{"id":1,' + bytes([128, len(tail)]) + tail)
                        _, ready = receive()
                        self.assertEqual(json.loads(ready)['method'], 'initialized')
                except BaseException as error:
                    failures.append(error)
            thread = threading.Thread(target=serve, daemon=True); thread.start()
            rpc = cs.Rpc(path)
            self.assertEqual(rpc.server_version, '0.160.0')
            rpc.close()
            thread.join(4)
            self.assertFalse(thread.is_alive())
            if failures: raise failures[0]


if __name__ == '__main__': unittest.main()
