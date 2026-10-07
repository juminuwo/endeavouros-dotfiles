#!/usr/bin/env python3
"""Stdlib, local-only Career adapter. Tracker and profile inputs are read-only.

The workspace JSON is authoritative. A stable sidecar flock serializes mutations;
readers see atomic snapshots. Packs precede the state commit; failed commits leave
an explicitly reported orphan, never a fabricated draft. The board is a projection
whose content mismatch is detectable without writing during list/context.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

DEFAULT_ROOT = Path('/home/howis/Documents/online-personal/Personal/Career')
STATUSES = {'unseen', 'reviewed', 'shortlisted', 'dismissed', 'draft', 'applied'}
ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z')
PROFILE = {'Adrian CV.md': 32000, 'Adrian CV References.md': 32000,
           'Search State.md': 16000, 'Career Workflow.md': 16000,
           'Next Employment Strategy.md': 16000}


class Error(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.payload = {'error': message, 'code': code, **details}


def clean(value):
    """Remove ANSI sequences and terminal controls, preserving prose whitespace."""
    if isinstance(value, str):
        value = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', value)
        value = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', value)
        return ''.join(c for c in value if c in '\n\t' or unicodedata.category(c) not in {'Cc', 'Cf', 'Cs'})
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def job_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise Error('invalid_id', 'Job ID must contain only letters, digits, underscores or hyphens.')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, code):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Error(code, f'Cannot read {path}: {exc}') from exc


def atomic_write(path, content):
    """Replace only after a complete, flushed file; never truncate the old file."""
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Backend:
    def __init__(self, root=DEFAULT_ROOT, cache=None):
        self.root = Path(root).resolve()
        self.state_path = self.root / 'data/career-workspace.json'
        self.inventory_path = self.root / 'Job Market/data/job-listings.json'
        self.cache = Path(cache) if cache is not None else Path.home() / '.cache/job-market-tracker/descriptions'

    def safe_path(self, relative):
        path = self.root / relative
        # Reject symlinked output components, including broken links.
        for part in (path, *path.parents):
            if part == self.root:
                break
            if part.is_symlink():
                raise Error('unsafe_path', f'Symlinked workspace output: {part}')
        if not path.resolve().is_relative_to(self.root):
            raise Error('unsafe_path', 'Output escapes Career root.')
        return path

    def inventory(self):
        data = read_json(self.inventory_path, 'invalid_inventory')
        if not isinstance(data, dict) or not isinstance(data.get('jobs'), dict):
            raise Error('invalid_inventory', 'Inventory must contain a jobs map.')
        if data.get('updated_at') is not None and not isinstance(data['updated_at'], str):
            raise Error('invalid_inventory', 'Inventory updated_at must be a timestamp string or null.')
        for key, row in data['jobs'].items():
            try:
                job_id(key)
                if not isinstance(row, dict) or row.get('id', key) != key:
                    raise ValueError('invalid record')
                for nested in ('user', 'scoring'):
                    if nested in row and not isinstance(row[nested], dict):
                        raise ValueError(f'invalid {nested}')
                if row.get('user', {}).get('status', 'unseen') not in tuple(STATUSES):
                    raise ValueError('invalid legacy status')
            except (Error, TypeError, ValueError) as exc:
                raise Error('invalid_inventory', f'Invalid inventory job {key}: {exc}') from exc
        return data

    def state(self):
        path = self.safe_path('data/career-workspace.json')
        if not path.exists():
            return {'schema_version': 1, 'jobs': {}, 'requests': {}, 'updated_at': None}
        state = read_json(path, 'invalid_state')
        try:
            if (not isinstance(state, dict) or state.get('schema_version') != 1
                    or not isinstance(state['jobs'], dict) or not isinstance(state['requests'], dict)):
                raise ValueError('invalid workspace schema')
            if state.get('updated_at') is not None and not isinstance(state['updated_at'], str):
                raise ValueError('invalid updated_at')
            for key, row in state['jobs'].items():
                job_id(key)
                if (not isinstance(row, dict) or row['status'] not in STATUSES
                        or type(row['revision']) is not int or row['revision'] < 1
                        or not isinstance(row['snapshot'], dict) or row['snapshot'].get('id') != key):
                    raise ValueError('invalid decision')
                if not isinstance(row.get('history', []), list):
                    raise ValueError('invalid history')
                for field in ('updated_at', 'applied_at'):
                    if row.get(field) is not None and not isinstance(row[field], str):
                        raise ValueError(f'invalid {field}')
                if 'pack_path' in row:
                    if not re.fullmatch(r'Applications/' + re.escape(key) + r'/Application-v\d{3,}\.md', row['pack_path']):
                        raise ValueError('invalid pack path')
            for key, entry in state['requests'].items():
                if (not isinstance(key, str) or not isinstance(entry, dict)
                        or not isinstance(entry['digest'], str)
                        or not isinstance(entry['result'], dict)
                        or entry['result'].get('committed') is not True):
                    raise ValueError('invalid request record')
                job_id(entry['job_id'])
        except (KeyError, TypeError, ValueError, Error) as exc:
            raise Error('invalid_state', f'Malformed workspace state: {exc}') from exc
        return state

    @contextmanager
    def locked(self):
        directory = self.safe_path('data')
        directory.mkdir(parents=True, exist_ok=True)
        lock = self.safe_path('data/career-workspace.lock')
        with lock.open('a', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def jobs(self, inventory, state):
        result = {}
        for key, row in inventory['jobs'].items():
            scoring = row.get('scoring', {})
            user = row.get('user', {})
            result[key] = clean({
                'id': key, **{field: row.get(field) for field in
                             ('title', 'company', 'location', 'workplace', 'salary', 'last_seen')},
                'url': row.get('canonical_url') or row.get('url'),
                'lifecycle': row.get('lifecycle', 'unknown'),
                'status': user.get('status', 'unseen'), 'revision': 0,
                'updated_at': None, 'applied_at': None,
                'score': scoring.get('total'),
                'priority': user.get('priority_override') or scoring.get('priority'),
                **{field: scoring.get(field) or [] for field in ('matches', 'gaps', 'uncertainties')},
                'summary': scoring.get('summary') or row.get('summary_excerpt') or '',
            })
        for key, decision in state['jobs'].items():
            if key not in result:
                result[key] = dict(decision['snapshot'], lifecycle='missing')
            result[key].update({field: decision[field] for field in ('status', 'revision')})
            result[key].update({field: decision.get(field) for field in ('updated_at', 'applied_at')})
            if decision.get('pack_path'):
                result[key]['pack_path'] = decision['pack_path']
        return result

    def board(self, state):
        lines = ['---', 'type: index', 'status: active', '---', '', '# Career Board', '',
                 'Generated from data/career-workspace.json. Use the Career workspace to change decisions.', '']
        for key, decision in sorted(state['jobs'].items()):
            row = decision['snapshot']
            title = str(row.get('title') or key).replace('\n', ' ')
            company = str(row.get('company') or '').replace('\n', ' ')
            lines.append(f'- **{decision["status"]}** — {title} · {company} (`{key}`, revision {decision["revision"]})')
            if decision.get('applied_at'):
                lines.append(f'  - Applied: {decision["applied_at"][:10]}')
            if decision.get('pack_path'):
                lines.append(f'  - [[{decision["pack_path"]}|Application pack]]')
        return clean('\n'.join(lines) + '\n')

    def board_warning(self, state):
        if not state['jobs']:
            return None
        try:
            if self.safe_path('Career Board.md').read_text(encoding='utf-8') == self.board(state):
                return None
        except (OSError, UnicodeError, Error):
            pass
        return 'Career Board projection pending; run refresh-board to recover. JSON state is authoritative.'

    def project(self, state):
        try:
            for key, decision in state['jobs'].items():
                if not decision.get('pack_path'):
                    continue
                index = self.safe_path(f'Applications/{key}/{key}.md')
                versions = sorted(index.parent.glob('Application-v*.md'))
                content = ('---\ntype: index\nstatus: active\n---\n\n# ' + key +
                           '\n\nVersioned application drafts. Submission is recorded separately in [[Career Board]].\n\n' +
                           '\n'.join(f'- [[Applications/{key}/{p.stem}]]' for p in versions) + '\n')
                atomic_write(index, content)
            if any(d.get('pack_path') for d in state['jobs'].values()):
                index = self.safe_path('Applications/Applications.md')
                if not index.exists():
                    atomic_write(index, '---\ntype: index\nstatus: active\n---\n\n# Applications\n\nSee [[Career Board]] for roles, stages and versioned application drafts.\n')
            atomic_write(self.safe_path('Career Board.md'), self.board(state))
            return None
        except (OSError, Error) as exc:
            return f'Career Board projection pending: {exc}. Run refresh-board; JSON state is committed.'

    def list(self):
        inventory, state = self.inventory(), self.state()
        result = {'jobs': list(self.jobs(inventory, state).values()),
                  'inventory_updated_at': inventory.get('updated_at'),
                  'workspace_updated_at': state.get('updated_at'),
                  'updated_at': max(filter(None, [inventory.get('updated_at'), state.get('updated_at')]), default=None)}
        warning = self.board_warning(state)
        if warning:
            result.update(warning=warning, board_warning=warning)
        return clean(result)

    def context(self, key):
        job_id(key)
        listing = self.list()
        job = next((job for job in listing['jobs'] if job['id'] == key), None)
        if job is None:
            raise Error('not_found', f'Unknown job: {key}')
        result = {'job': job, 'profile': {}, 'profile_truncated': [], 'profile_missing': []}
        for name, limit in PROFILE.items():
            try:
                with (self.root / name).open(encoding='utf-8') as stream:
                    content = stream.read(limit + 1)
                result['profile'][name] = content[:limit]
                if len(content) > limit:
                    result['profile_truncated'].append(name)
            except FileNotFoundError:
                result['profile_missing'].append(name)
        path = self.cache / (key + '.json')
        if path.exists():
            try:
                cached = read_json(path, 'invalid_cache')
                stamp = datetime.fromisoformat(cached['cached_at'].replace('Z', '+00:00'))
                current = datetime.now(timezone.utc)
                if (cached.get('job_id') == key and isinstance(cached.get('description'), str)
                        and current - timedelta(days=7) <= stamp <= current):
                    result.update(description=cached['description'], description_cached_at=cached['cached_at'])
            except (Error, KeyError, TypeError, ValueError, AttributeError):
                result['description_warning'] = 'Cached description malformed; omitted.'
        if 'warning' in listing:
            result['warning'] = listing['warning']
        return clean(result)

    def check(self, job, target, expected, revision):
        if expected not in tuple(STATUSES) or target not in tuple(STATUSES):
            raise Error('invalid_status', 'Unknown status.')
        if revision is not None and (type(revision) is not int or revision < 0):
            raise Error('invalid_revision', 'Expected revision must be a nonnegative integer.')
        if revision is not None and revision != job['revision']:
            raise Error('conflict', 'Job revision changed; reload before retrying.')
        if job['status'] == target:
            return
        if job['status'] != expected:
            raise Error('conflict', 'Job status changed; reload before retrying.')
        if job['status'] == 'dismissed' and target == 'applied':
            raise Error('dismissed_guard', 'Restore a dismissed job before marking it applied.')
        if job['status'] == 'applied':
            raise Error('applied_guard', 'Applied jobs cannot be downgraded.')
        if target in {'shortlisted', 'draft', 'applied'} and job['lifecycle'] != 'active':
            raise Error('inactive_guard', 'Inactive or missing jobs cannot newly advance.')

    def commit(self, state):
        state['updated_at'] = now()
        atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, indent=2) + '\n')

    def mutate(self, key, target=None, expected=None, revision=None, pack=None):
        job_id(key)
        digest = None
        if pack is None and target == 'draft':
            raise Error('draft_requires_pack', 'Use save-pack to create a draft with an application artifact.')
        if pack is not None:
            if not isinstance(pack, dict):
                raise Error('invalid_pack', 'Pack input must be a JSON object.')
            content, request = pack.get('content'), pack.get('request_id')
            if not isinstance(content, str) or len(re.findall(r'\w+', clean(content))) < 20 or not re.search(r'(?m)^\s*(?:#{1,6} |[-*] |\d+\. )', content):
                raise Error('invalid_pack', 'Pack must contain substantive Markdown (at least 20 words and a heading or list).')
            if not isinstance(request, str) or not request.strip() or len(request) > 256:
                raise Error('invalid_request_id', 'request_id must be a nonempty string of at most 256 characters.')
            if 'expected_revision' not in pack or type(pack['expected_revision']) is not int or pack['expected_revision'] < 0:
                raise Error('invalid_revision', 'save-pack requires a nonnegative expected_revision.')
            expected, revision = pack.get('expected'), pack['expected_revision']
            digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        with self.locked():
            state = self.state()
            if pack is not None and request in state['requests']:
                previous = state['requests'][request]
                if previous['job_id'] != key or previous['digest'] != digest:
                    raise Error('request_conflict', 'request_id already belongs to a different job or content.')
                result = dict(previous['result'])
                warning = self.project(state)
                if warning:
                    result['warning'] = warning
                return clean(result)
            inventory = self.inventory()
            job = self.jobs(inventory, state).get(key)
            if job is None:
                raise Error('not_found', f'Unknown job: {key}')
            if pack is not None:
                if job['lifecycle'] != 'active':
                    raise Error('inactive_guard', 'Inactive or missing jobs cannot receive new application packs.')
                target = 'applied' if job['status'] == 'applied' else 'draft'
                # Pack creation always requires the caller's exact observed state.
                if job['status'] != expected:
                    raise Error('conflict', 'Job status changed; reload before saving a pack.')
            self.check(job, target, expected, revision)
            if pack is None and job['status'] == target and key in state['jobs']:
                result = {'job': job, 'committed': True}
                warning = self.project(state)
                if warning:
                    result['warning'] = warning
                return clean(result)
            path = None
            if pack is not None:
                directory = self.safe_path(f'Applications/{key}')
                directory.mkdir(parents=True, exist_ok=True)
                versions = [int(m.group(1)) for p in directory.iterdir()
                            if (m := re.fullmatch(r'Application-v(\d+)\.md', p.name))]
                path = self.safe_path(f'Applications/{key}/Application-v{max(versions, default=0) + 1:03d}.md')
                try:
                    # Exclusive creation preserves every earlier version, including orphans.
                    with path.open('x', encoding='utf-8') as stream:
                        frontmatter = '' if content.startswith('---\n') else (
                            '---\ntype: reference\nstatus: draft\ndate: ' + now()[:10] + '\n---\n\n')
                        stream.write(frontmatter + content)
                        stream.flush()
                        os.fsync(stream.fileno())
                except OSError as exc:
                    raise Error('pack_write_failed', f'Application pack could not be saved: {exc}',
                                **({'orphan_path': str(path)} if path.exists() else {})) from exc
            stamp = now()
            applied_at = job.get('applied_at')
            if target == 'applied' and job['status'] != 'applied':
                applied_at = stamp
            updated = dict(job, status=target, revision=job['revision'] + 1,
                           updated_at=stamp, applied_at=applied_at)
            if path:
                updated['pack_path'] = str(path.relative_to(self.root))
            history = list(state['jobs'].get(key, {}).get('history', []))
            history.append({'from': job['status'], 'to': target, 'at': stamp,
                            'revision': updated['revision'],
                            'action': 'save-pack' if pack is not None else 'status'})
            decision = {'status': target, 'revision': updated['revision'], 'snapshot': updated,
                        'updated_at': stamp, 'applied_at': applied_at, 'history': history}
            if updated.get('pack_path'):
                decision['pack_path'] = updated['pack_path']
            state['jobs'][key] = decision
            result = {'job': updated, 'committed': True}
            if path:
                result['pack_path'] = updated['pack_path']
                state['requests'][request] = {'job_id': key, 'digest': digest, 'result': result.copy()}
            try:
                self.commit(state)
            except OSError as exc:
                raise Error('state_write_failed', f'Workspace state was not committed: {exc}',
                            **({'orphan_path': str(path)} if path else {})) from exc
            warning = self.project(state)
            if warning:
                result['warning'] = warning
            return clean(result)

    def refresh_board(self):
        with self.locked():
            state = self.state()
            warning = self.project(state)
            if warning:
                raise Error('projection_failed', warning)
            return {'refreshed': True, 'board_path': 'Career Board.md'}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Error('usage', message)


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
        commands = parser.add_subparsers(dest='command', required=True)
        commands.add_parser('list')
        commands.add_parser('refresh-board')
        context = commands.add_parser('context')
        context.add_argument('job_id')
        status = commands.add_parser('status')
        status.add_argument('job_id')
        status.add_argument('status')
        status.add_argument('--expected', required=True)
        status.add_argument('--expected-revision', type=int)
        pack = commands.add_parser('save-pack')
        pack.add_argument('job_id')
        args = parser.parse_args(argv)
        backend = Backend(args.root)
        if args.command == 'list':
            result = backend.list()
        elif args.command == 'context':
            result = backend.context(args.job_id)
        elif args.command == 'refresh-board':
            result = backend.refresh_board()
        elif args.command == 'status':
            result = backend.mutate(args.job_id, args.status, args.expected, args.expected_revision)
        else:
            try:
                payload = json.load(sys.stdin)
            except ValueError as exc:
                raise Error('invalid_pack', f'Invalid JSON input: {exc}') from exc
            result = backend.mutate(args.job_id, pack=payload)
        print(json.dumps(clean(result), ensure_ascii=False))
        return 0
    except Error as exc:
        print(json.dumps(clean(exc.payload), ensure_ascii=False))
        return 1
    except (OSError, UnicodeError) as exc:
        print(json.dumps(clean({'error': str(exc), 'code': 'io_error'}), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
