"""Fixed diagnostic operations. Never install, repair, publish or capture audio."""
import datetime
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.parse import urlsplit, urljoin, urlencode
import xml.etree.ElementTree as ET

ROOT = Path('C:/AI/AI Native')
TOOLS = Path('C:/AI/Tools')
PYTHON = TOOLS / '.dion-secretary/venv/Scripts/python.exe'
GH = TOOLS / 'github-publishing/github-cli/bin/gh.exe'
REPOS = {'skills': 'Vaakom/agent-skills', 'dion': 'Vaakom/dion-speaker-helper',
         'permissions': 'Vaakom/local-permissions'}
TESTS = {
    'permissions': ('local-permissions', ['-m', 'unittest', 'test_dispatch', 'test_submit', 'test_operations']),
    'dion-helper': ('dion-speaker-helper', ['-m', 'unittest', 'test_helper', 'test_hybrid', 'test_browser_names', 'test_auto_journals', 'test_install']),
    'archive': ('obsidian-history', ['-m', 'unittest', 'test_archive']),
    'skill-health': ('skill-health', ['-m', 'unittest', 'test_audit']),
}


def validate(req):
    if not isinstance(req, dict):
        raise ValueError('Request object required')
    op = req.get('operation')
    allowed = {
        'tests': ({'operation', 'suite'}, 'suite', TESTS),
        'diagnostic': ({'operation', 'component'}, 'component', {'dion', 'syncthing', 'archive'}),
        'github': ({'operation', 'action', 'repo'}, 'action', {'auth', 'refs', 'ci'}),
        'link': ({'operation', 'url'}, None, None),
    }
    if op not in allowed:
        raise ValueError('Unknown diagnostic operation')
    fields, key, values = allowed[op]
    if set(req) - fields:
        raise ValueError('Unknown operation fields')
    if key and (not isinstance(req.get(key), str) or req[key] not in values):
        raise ValueError('Unknown operation selector')
    if op == 'github':
        if req['action'] == 'auth':
            if 'repo' in req:
                raise ValueError('Auth takes no repo')
        elif not isinstance(req.get('repo'), str) or req['repo'] not in REPOS:
            raise ValueError('Unknown repository')
    if op == 'link':
        public_url(req.get('url'), resolve=False)
    return req


def plan(req):
    validate(req)
    # JSON is an argv value, never interpreted by a shell.
    return ('exec', [str(PYTHON), '-X', 'utf8', '-B', str(Path(__file__).resolve()),
                     json.dumps(req, ensure_ascii=False)])


def public_url(url, resolve=True):
    if not isinstance(url, str) or not url or len(url) > 8192 or '\\' in url or any(ord(c) <= 32 for c in url):
        raise ValueError('Invalid URL')
    u = urlsplit(url)
    if u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password:
        raise ValueError('Public HTTP(S) URL required, without credentials')
    if u.port not in {None, 80 if u.scheme == 'http' else 443}:
        raise ValueError('Nonstandard port rejected')
    host = u.hostname.encode('idna').decode('ascii')
    if not resolve:
        return u, host, None
    port = u.port or (443 if u.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Local/private network destination rejected')
    return u, host, addresses[0][4][0]


def check_link(url):
    for _ in range(6):
        u, host, ip = public_url(url)
        conn = (http.client.HTTPSConnection if u.scheme == 'https' else http.client.HTTPConnection)(host, timeout=15)
        # Pin the validated address; HTTPS still verifies the original hostname.
        conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection((ip, address[1]), timeout, source_address)
        try:
            path = u.path or '/'
            if u.query:
                path += '?' + u.query
            conn.request('GET', path, headers={'User-Agent': 'LocalPermissions-LinkCheck/1.0'})
            response = conn.getresponse()
            status = response.status
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirect without destination')
                next_url = urljoin(url, location)
                if u.scheme == 'https' and urlsplit(next_url).scheme != 'https':
                    raise ValueError('HTTPS downgrade rejected')
                url = next_url
                continue
            body = response.read(65536).decode('utf-8', errors='replace')
            title = re.search(r'<title[^>]*>(.*?)</title>', body, re.I | re.S)
            return {'status': status, 'ok': 200 <= status < 300,
                    'title': re.sub(r'\s+', ' ', title.group(1)).strip()[:512] if title else None}
        finally:
            conn.close()
    raise ValueError('Too many redirects')


def load_json(path):
    return json.loads(path.read_text('utf-8-sig'))


def diagnostic(component):
    if component == 'dion':
        local_path = Path(os.environ['LOCALAPPDATA']) / 'DionSpeakerHelper/config.json'
        local = load_json(local_path if local_path.is_file() else ROOT / 'products/dion-speaker-helper/config.local.json')
        runtime = Path(local['runtime'])
        cfg = load_json(runtime / 'host-config.json')
        manifest = load_json(runtime / 'native-host.json')
        expected = 'chrome-extension://' + local['extension_id'] + '/'
        recent = []
        now = datetime.datetime.now().timestamp()
        for path in (runtime / 'journals').glob('*/*/events.jsonl'):
            st = path.stat()
            if now - st.st_mtime < 120:
                recent.append({'journal': path.parent.name, 'bytes': st.st_size, 'age_seconds': round(now-st.st_mtime, 1)})
        return {'origin_matches_local_config': cfg.get('origin') == expected and manifest.get('allowed_origins') == [expected],
                'recent_journals': recent, 'limitation': 'Fresh files alone do not prove names or actual Chrome extension identity.'}
    if component == 'archive':
        status = load_json(TOOLS / 'obsidian-history/status.json')
        # Exclude raw error messages and source paths from diagnostics.
        return {k: status.get(k) if k != 'errors' else len(status.get(k, []))
                for k in ('checked_utc', 'pid', 'matched', 'changed', 'errors')}
    # Exact loopback service and fixed folder; never accept a user-supplied API path/key.
    config = ET.parse(Path(os.environ['LOCALAPPDATA']) / 'Syncthing/config.xml').getroot()
    key = config.findtext('gui/apikey')
    address = config.findtext('gui/address')
    if address != '127.0.0.1:8384' or not key:
        raise ValueError('Expected loopback Syncthing service unavailable')
    result = {}
    for endpoint, fields in [('status', ('state', 'errors', 'needFiles', 'needBytes')),
                             ('ignores', ('ignore',))]:
        conn = http.client.HTTPConnection('127.0.0.1', 8384, timeout=10)
        try:
            conn.request('GET', '/rest/db/' + endpoint + '?' + urlencode({'folder': 'elkkp-mpxnv'}), headers={'X-API-Key': key})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError('Syncthing status request failed')
            data = json.loads(response.read(1048576))
            result[endpoint] = {k: data.get(k) for k in fields}
        finally:
            conn.close()
    return result


def execute(req):
    validate(req)
    op = req['operation']
    if op == 'tests':
        directory, args = TESTS[req['suite']]
        return subprocess.run([str(PYTHON), '-X', 'utf8', '-B', *args], cwd=ROOT/'products'/directory,
                              shell=False, timeout=300).returncode
    if op == 'github':
        if req['action'] == 'auth':
            # Avoid auth status output, which includes token metadata.
            r = subprocess.run([str(GH), 'api', 'user', '--jq', '.login'], capture_output=True, text=True, timeout=30)
            print(json.dumps({'authenticated': r.returncode == 0, 'login': r.stdout.strip() if r.returncode == 0 else None}))
            return r.returncode
        repo = REPOS[req['repo']]
        args = (['api', 'repos/' + repo + '/git/ref/heads/main', '--jq', '.object.sha'] if req['action'] == 'refs'
                else ['run', 'list', '--repo', repo, '--limit', '5', '--json', 'databaseId,status,conclusion,headSha'])
        return subprocess.run([str(GH), *args], shell=False, timeout=30).returncode
    result = check_link(req['url']) if op == 'link' else diagnostic(req['component'])
    print(json.dumps(result, ensure_ascii=False))
    return 1 if op == 'link' and not result['ok'] else 0


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('One validated JSON argument required')
        raise SystemExit(execute(json.loads(sys.argv[1])))
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        # Do not echo URLs, service keys, config content or subprocess credentials.
        print(json.dumps({'state': 'unavailable', 'error_type': type(exc).__name__}))
        raise SystemExit(2)
