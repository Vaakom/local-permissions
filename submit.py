"""Validate one JSON request from stdin and atomically enqueue it; never execute it."""
import json
import base64
import os
from pathlib import Path
import sys
import tempfile

from run import STATE, REQUEST, build_plan

MAX_BYTES = 65536


def enqueue(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Request must be 1..65536 bytes')
    req = json.loads(raw.decode('utf-8-sig'))
    build_plan(req)
    STATE.mkdir(parents=True, exist_ok=True)
    if (STATE / 'dispatch.lock').exists() or (STATE / 'processing.json').exists():
        raise ValueError('Another operation is in progress')
    # Hard-link publication is atomic and refuses to overwrite a pending request.
    fd, name = tempfile.mkstemp(prefix='request-', suffix='.tmp', dir=STATE)
    pending = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, REQUEST)
    finally:
        pending.unlink(missing_ok=True)
    return {'state': 'queued', 'operation': req['operation'],
            'action': req.get('action', req.get('check'))}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--json-base64':
        raw = base64.b64decode(sys.argv[2], validate=True)
    elif len(sys.argv) == 3 and sys.argv[1] == '--json':
        raw = sys.argv[2].encode('utf-8')
    elif len(sys.argv) == 1:
        print('Ready for one JSON request line on stdin.', flush=True)
        raw = sys.stdin.buffer.readline(MAX_BYTES + 1)
    else:
        raise ValueError('Use stdin, --json, or --json-base64 with one request')
    print(json.dumps(enqueue(raw)), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
        print('Local request rejected:', type(exc).__name__, str(exc), file=sys.stderr)
        raise SystemExit(2)
