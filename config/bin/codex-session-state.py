"""Read-only Codex daemon session discovery; Linux and Python stdlib only.

The daemon owns history, while each TUI owns a loopback MCP listener. Match
that live socket to the thread's codex_tui origin, never by cwd or recency.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import time
import uuid


class RpcError(RuntimeError):
    def __init__(self, method, error):
        super().__init__(f'Codex {method} failed: {error}')
        self.code = error.get('code')
        self.message = error.get('message')


class Rpc:
    """Bounded WebSocket JSON-RPC client for Codex's local Unix socket."""
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(8)
        self.stream = None
        self.sequence = 0
        self.server_version = 'unknown'
        self.operation = f'connect/handshake ({path})'
        self.deadline = time.monotonic() + 60
        try:
            self.sock.connect(str(path))
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((f'GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                               f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                               'Sec-WebSocket-Version: 13\r\n\r\n').encode())
            self.stream = self.sock.makefile('rb')
            headers = bytearray()
            while not headers.endswith(b'\r\n\r\n'):
                headers.extend(self.read(1))
                if len(headers) > 16384:
                    raise RuntimeError('Oversized Codex handshake')
            lines = headers.decode('ascii').split('\r\n')
            fields = {k.lower(): v.strip() for k, v in (line.split(':', 1) for line in lines[1:] if ':' in line)}
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if lines[0].split()[1] != '101' or fields.get('sec-websocket-accept') != expected:
                raise RuntimeError('Invalid Codex WebSocket handshake')
            initialized = self.call('initialize', {'clientInfo': {'name': 'desktop-session', 'version': '1'},
                                                  'capabilities': {'experimentalApi': True}})
            agent = initialized.get('userAgent', '').split(' ', 1)[0]
            self.server_version = agent.rsplit('/', 1)[-1]
            self.send(json.dumps({'method': 'initialized'}).encode())
        except TimeoutError as error:
            self.close()
            raise RuntimeError(f'Codex {self.operation} timed out (8s socket limit)') from error
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.stream:
            self.stream.close()
        self.sock.close()

    def read(self, size):
        if time.monotonic() >= self.deadline:
            raise RuntimeError(f'Codex {self.operation} exceeded the 60s discovery deadline')
        self.sock.settimeout(min(8, max(.01, self.deadline - time.monotonic())))
        data = self.stream.read(size)
        if len(data) != size:
            raise RuntimeError('Codex session connection closed')
        return data

    def send(self, data, opcode=1):
        mask = os.urandom(4)
        size = len(data)
        if size < 126:
            header = bytes([128 | opcode, 128 | size])
        elif size < 65536:
            header = bytes([128 | opcode, 254]) + struct.pack('!H', size)
        else:
            header = bytes([128 | opcode, 255]) + struct.pack('!Q', size)
        self.sock.sendall(header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def receive(self):
        message = bytearray()
        started = False
        while True:
            first, second = self.read(2)
            opcode = first & 15
            size = second & 127
            if first & 112 or second & 128:
                raise RuntimeError('Unsupported Codex WebSocket frame')
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            if size + len(message) > 16 * 1024 * 1024:
                raise RuntimeError('Oversized Codex response')
            data = self.read(size)
            if opcode in (9, 10):
                if not first & 128 or size > 125:
                    raise RuntimeError('Invalid Codex control frame')
                if opcode == 9:
                    self.send(data, 10)
                continue
            if opcode == 8:
                raise RuntimeError('Codex session connection closed')
            if opcode != (0 if started else 1):
                raise RuntimeError('Unsupported Codex message')
            started = True
            message.extend(data)
            if first & 128:
                return json.loads(message)

    def call(self, method, params):
        self.operation = method + (f" (thread {params['threadId']})" if params.get('threadId') else '')
        if method == 'mcpServerStatus/list':
            # The pinned daemon can lag behind the CLI. 0.157.1 ignores this
            # filter and probes every remote MCP server's OAuth endpoints.
            # 0.160.0 is the first version verified locally with this filter.
            version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', self.server_version)
            if not version or tuple(map(int, version.groups())) < (0, 160, 0):
                raise RuntimeError(f'Codex daemon {self.server_version} cannot perform local-only session discovery; '
                                   'update the pinned daemon with: codex app-server daemon update --from-cli --yes')
            if params.get('serverName') != 'codex_tui' or not params.get('threadId'):
                raise RuntimeError('Session discovery requires a thread-scoped codex_tui filter')
        self.sequence += 1
        try:
            self.send(json.dumps({'id': self.sequence, 'method': method, 'params': params}).encode())
            while True:
                result = self.receive()
                if result.get('id') == self.sequence:
                    if 'error' in result:
                        raise RpcError(method, result['error'])
                    return result['result']
        except TimeoutError as error:
            raise RuntimeError(f'Codex {self.operation} timed out (8s socket limit)') from error

    def pages(self, method, params):
        params = dict(params)
        seen = set()
        while True:
            result = self.call(method, params)
            yield from result['data']
            cursor = result.get('nextCursor')
            if not cursor:
                return
            if cursor in seen:
                raise RuntimeError('Codex repeated a pagination cursor')
            seen.add(cursor)
            params['cursor'] = cursor


def process_identity(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def listener_origins(pid):
    inodes = set()
    for fd in Path(f'/proc/{pid}/fd').iterdir():
        try:
            target = str(fd.readlink())
        except FileNotFoundError:
            continue
        if target.startswith('socket:['):
            inodes.add(target[8:-1])
    origins = set()
    # Only accept IPv4 loopback listeners, as advertised by the local TUI.
    for line in Path(f'/proc/{pid}/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        address, port = fields[1].split(':')
        if fields[3] == '0A' and fields[9] in inodes and address == '0100007F':
            origins.add(f'http://127.0.0.1:{int(port, 16)}')
    return origins


def daemon_roots(home):
    rpc = Rpc(home / 'app-server-control/app-server-control.sock')
    try:
        roots = []
        for sid in rpc.pages('thread/loaded/list', {}):
            thread = rpc.call('thread/read', {'threadId': sid, 'includeTurns': False})['thread']
            # source records where a thread was created, not its current UI.
            if thread.get('parentThreadId') or isinstance(thread.get('source'), dict):
                continue
            saved = persisted(thread)
            if not saved and unused_startup_thread(rpc, thread):
                continue
            session = {'id': str(uuid.UUID(thread['id'])), 'cwd': thread['cwd']}
            if not isinstance(session['cwd'], str) or not Path(session['cwd']).is_absolute():
                raise RuntimeError('Invalid Codex conversation directory')
            for server in rpc.pages('mcpServerStatus/list', {
                    'threadId': sid, 'serverName': 'codex_tui', 'detail': 'toolsAndAuthOnly'}):
                if server['name'] != 'codex_tui':
                    raise RuntimeError('Codex daemon ignored the local-only MCP filter; update the daemon')
                if server['name'] == 'codex_tui' and server.get('httpOrigin'):
                    status = server.get('runtimeStatus') if saved else 'unrestorable'
                    roots.append((server['httpOrigin'], status, session))
        return roots
    finally:
        rpc.close()


def unused_startup_thread(rpc, thread):
    # Resuming can leave an unused initial thread on the same TUI endpoint.
    # Absence of a file alone is insufficient: require the server to confirm
    # that it has never received a user message. Final capture rechecks this.
    if (thread.get('ephemeral') or thread.get('name') or thread.get('preview') or
            thread.get('status', {}).get('type') != 'idle' or
            (thread.get('path') and Path(thread['path']).exists())):
        return False
    try:
        rpc.call('thread/turns/list', {'threadId': thread['id'], 'limit': 1})
    except RpcError as error:
        expected = (f"thread {thread['id']} is not materialized yet; "
                    'thread/turns/list is unavailable before first user message')
        if error.code == -32600 and error.message == expected:
            return True
        raise
    return False


def persisted(thread):
    if thread.get('ephemeral') or not thread.get('path'):
        return False
    try:
        with Path(thread['path']).open() as stream:
            event = json.loads(stream.readline(1024 * 1024))
        return event.get('type') == 'session_meta' and event.get('payload', {}).get('id') == thread['id']
    except (OSError, ValueError):
        return False


_cache = None
_observed = {}


def begin_capture():
    global _cache, _observed
    _cache, _observed = {}, {}


def resolve(pid, home):
    identity = process_identity(pid)
    origins = listener_origins(pid)
    if not origins:
        return None
    if not (home / 'app-server-control/app-server-control.sock').exists():
        raise RuntimeError(f'Cannot reach the Codex daemon for PID {pid}')
    if _cache is None:
        roots = daemon_roots(home)
    else:
        if home not in _cache:
            _cache[home] = daemon_roots(home)
        roots = _cache[home]
    matches = [(status, session) for origin, status, session in roots if origin in origins]
    if len(matches) != 1 or matches[0][0] != 'connected':
        raise RuntimeError(f'Cannot identify one connected, saved Codex conversation for PID {pid}; '
                           'close unused tasks in this tab or reopen the intended conversation in a new tab')
    if process_identity(pid) != identity or listener_origins(pid) != origins:
        raise RuntimeError('Codex process changed during capture; retry')
    result = matches[0][1]
    if _cache is not None:
        record = (home, identity, origins, result)
        if pid in _observed and _observed[pid] != record:
            raise RuntimeError('Codex conversation changed during capture; retry')
        _observed[pid] = record
    return dict(result)


def verify_capture():
    """Re-query before publication, not just the cached per-pane discovery."""
    global _cache, _observed
    observed = _observed
    _cache, _observed = None, {}
    fresh = {home: daemon_roots(home) for home in {r[0] for r in observed.values()}}
    for pid, (home, identity, origins, session) in observed.items():
        matches = [(status, candidate) for origin, status, candidate in fresh[home] if origin in origins]
        if (process_identity(pid) != identity or listener_origins(pid) != origins or
                matches != [('connected', session)]):
            raise RuntimeError('Codex conversation changed during capture; retry')
