"""Validated dispatcher for explicitly requested local operations. No shell execution."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urlsplit

VAULT = Path('C:/AI/AI Native')
STATE = Path('C:/AI/Tools/local-permissions')
REQUEST = STATE / 'request.json'
PYTHON = Path('C:/AI/Tools/.dion-secretary/venv/Scripts/python.exe')
SESSIONS = Path('C:/AI/Large files/Dion')
NOTES = VAULT / 'meetings/Dion'
JOURNALS = Path('C:/AI/Tools/dion-speaker-helper/runtime/journals')
DOCS = Path('C:/AI/Large files/documents')
SUFFIXES = {'.md', '.txt', '.pdf', '.docx', '.xlsx', '.csv', '.pptx',
            '.png', '.jpg', '.jpeg', '.webp', '.gif', '.html', '.htm'}


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError('Expected a nonempty bounded string')
    if any(ord(c) < 32 for c in value):
        raise ValueError('Control characters are not allowed')
    return value


def fields(req, allowed):
    if not isinstance(req, dict) or set(req) - set(allowed):
        raise ValueError('Unknown request fields')


def path_under(value, roots, *, exists=True, directory=False):
    raw = text(value)
    if raw.startswith(('\\\\', '//')) or ':' in raw[2:]:
        raise ValueError('UNC paths and alternate streams are not allowed')
    p = Path(raw)
    if not p.is_absolute():
        raise ValueError('Absolute path required')
    p = p.resolve(strict=exists)
    if not any(p != root.resolve() and p.is_relative_to(root.resolve()) for root in roots):
        raise ValueError('Path is outside permitted roots')
    if any(part.casefold() == 'private' or part.startswith('.') for part in p.parts[1:]):
        raise ValueError('Private and hidden paths require separate authorization')
    if exists and (p.is_dir() if directory else p.is_file()) is False:
        raise ValueError('Wrong path type')
    return p


def python(script, *args):
    return ('exec', [str(PYTHON), '-X', 'utf8', '-B', str(VAULT / script), *args])


def build_plan(req):
    if not isinstance(req, dict):
        raise ValueError('Request must be an object')
    op = req.get('operation')
    if op == 'dion':
        fields(req, {'operation', 'action', 'title', 'speaker', 'mic', 'session',
                     'meeting_journal', 'transcript', 'handoff', 'draft'})
        action = req.get('action')
        args = []
        accepted = {'operation', 'action'}
        if action == 'start':
            accepted |= {'title', 'speaker', 'mic', 'meeting_journal'}
            args += ['--title', text(req.get('title'))]
            for key in ('speaker', 'mic'):
                if key in req:
                    if type(req[key]) is not int or not 0 <= req[key] <= 10000:
                        raise ValueError('Invalid device index')
                    args += ['--' + key, str(req[key])]
            if 'meeting_journal' in req:
                args += ['--meeting-journal', str(path_under(req['meeting_journal'], [JOURNALS], directory=True))]
        elif action == 'process':
            accepted.add('session')
            args += ['--session', str(path_under(req.get('session'), [SESSIONS], directory=True)),
                     '--minutes-provider', 'codex', '--speaker-mode', 'browser']
        elif action == 'summarize':
            accepted.add('transcript')
            p = path_under(req.get('transcript'), [NOTES])
            if p.suffix.lower() != '.md':
                raise ValueError('Markdown transcript required')
            args += ['--transcript', str(p), '--minutes-provider', 'codex']
        elif action == 'finalize-minutes':
            accepted |= {'handoff', 'draft'}
            h = path_under(req.get('handoff'), [SESSIONS])
            d = path_under(req.get('draft'), [SESSIONS])
            if h.name != 'minutes-handoff.json' or d.parent != h.parent or d.suffix != '.md':
                raise ValueError('Handoff and Markdown draft must belong to one session')
            data = json.loads(h.read_text(encoding='utf-8'))
            path_under(data['transcript'], [NOTES])
            path_under(data['protocol'], [NOTES], exists=False)
            args += ['--handoff', str(h), '--draft', str(d)]
        elif action not in {'status', 'devices', 'stop'}:
            raise ValueError('Dion action is not allowed')
        fields(req, accepted)
        return python('skills/dion-secretary/scripts/secretary.py', action, *args)
    if op == 'mail':
        action = req.get('action')
        if action == 'export':
            fields(req, {'operation', 'action', 'sender', 'subjects', 'destination'})
            subjects = req.get('subjects')
            if not isinstance(subjects, list) or not 1 <= len(subjects) <= 30:
                raise ValueError('Nonempty subject filter list required')
            dest = path_under(req.get('destination'), [VAULT / 'output'], exists=False)
            args = ['--sender', text(req.get('sender')), '--destination', str(dest)]
            for item in subjects:
                args += ['--subject', text(item)]
            return python('products/yandex-mail/export_markdown.py', *args)
        if action not in {'check', 'folders', 'search', 'read'}:
            raise ValueError('Mail action is not allowed')
        allowed = {'operation', 'action'}
        args = [action]
        if action == 'search':
            allowed |= {'text', 'subject', 'sender', 'since', 'before', 'folders', 'all_folders', 'limit'}
            for key, flag in [('text', '--text'), ('subject', '--subject'), ('sender', '--from'),
                              ('since', '--since'), ('before', '--before')]:
                if key in req:
                    value = text(req[key])
                    if key in {'since', 'before'}:
                        datetime.date.fromisoformat(value)
                    args += [flag, value]
            limit = req.get('limit', 20)
            if type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError('Limit must be 1..100')
            args += ['--limit', str(limit)]
            if 'all_folders' in req and type(req['all_folders']) is not bool:
                raise ValueError('all_folders must be boolean')
            if req.get('all_folders'):
                if req.get('folders'):
                    raise ValueError('Choose all_folders or folders')
                args += ['--all-folders']
            folders = req.get('folders', [])
            if not isinstance(folders, list):
                raise ValueError('folders must be a list')
            for folder in folders:
                args += ['--folder', text(folder)]
        elif action == 'read':
            allowed |= {'folder', 'uid'}
            uid = text(req.get('uid'))
            if not uid.isascii() or not uid.isdigit():
                raise ValueError('Numeric UID required')
            args += ['--folder', text(req.get('folder')), '--uid', uid]
        fields(req, allowed)
        return python('products/yandex-mail/mail.py', *args)
    if op == 'open':
        fields(req, {'operation', 'target', 'anchor'})
        target = text(req.get('target'))
        u = urlsplit(target)
        if u.scheme.lower() in {'http', 'https'}:
            if not u.hostname or u.username or u.password or '\\' in target or 'anchor' in req:
                raise ValueError('Invalid web URL')
            return ('open', target)
        p = path_under(target, [VAULT, DOCS])
        if p.suffix.lower() not in SUFFIXES:
            raise ValueError('Unsupported document type')
        anchor = req.get('anchor')
        if p.suffix.lower() == '.md' and p.is_relative_to(VAULT.resolve()):
            suffix = ''
            if anchor is not None:
                anchor = text(anchor)
                if not anchor.startswith('^') or any(c not in '^abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in anchor):
                    raise ValueError('Only block anchors are accepted')
                suffix = '#' + anchor
            return ('open', 'obsidian://open?vault=' + quote(VAULT.name, safe='') +
                    '&file=' + quote(p.relative_to(VAULT.resolve()).as_posix() + suffix, safe=''))
        if anchor is not None:
            raise ValueError('Anchors require a vault Markdown note')
        return ('open', str(p))
    if op == 'audit':
        fields(req, {'operation', 'check'})
        check = req.get('check')
        if check == 'vault':
            return python('products/vault-maintenance/audit.py')
        flags = {'skills-static': ['--static-only'], 'skills-tests': ['--only', 'skills isolated tests'], 'skills-full': []}
        if check not in flags:
            raise ValueError('Unknown audit')
        return python('products/skill-health/audit.py', *flags[check], '--output',
                      'C:/AI/Tools/skill-health/reports/permissions-' + check + '.json')
    raise ValueError('Unknown operation')


def main():
    if len(sys.argv) != 1:
        raise ValueError('Dispatcher accepts no command-line arguments')
    STATE.mkdir(parents=True, exist_ok=True)
    # Exclusive lock prevents two callers executing the same request concurrently.
    lock = STATE / 'dispatch.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    claimed = STATE / 'processing.json'
    try:
        os.replace(REQUEST, claimed)
        data = claimed.read_bytes()
        if len(data) > 65536:
            raise ValueError('Request too large')
        req = json.loads(data.decode('utf-8-sig'))
        kind, payload = build_plan(req)
        # Metadata only: do not persist searches, credentials, URLs or message contents.
        (STATE / 'last-operation.json').write_text(json.dumps({
            'at': datetime.datetime.now().isoformat(), 'operation': req['operation'],
            'action': req.get('action', req.get('check')), 'state': 'running'
        }), encoding='utf-8')
        if kind == 'open':
            os.startfile(payload)
            return 0
        env = dict(os.environ)
        env.pop('DION_SECRETARY_CONFIG', None)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        return subprocess.run(payload, cwd=str(VAULT), env=env, shell=False).returncode
    finally:
        os.close(fd)
        # Request contents are not retained in the dispatcher runtime.
        claimed.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print('Local operation rejected:', type(exc).__name__, str(exc), file=sys.stderr)
        raise SystemExit(2)
