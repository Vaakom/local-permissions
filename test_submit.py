"""Synthetic enqueue tests: no recording, mail, browser or operation execution."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import submit as s


class SubmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='C:/AI/Tools/local-permissions')
        self.root = Path(self.tmp.name)
        self.request = self.root / 'request.json'
        self.patches = [patch.object(s, 'STATE', self.root), patch.object(s, 'REQUEST', self.request)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_status_is_queued_only(self):
        raw = b'{"operation":"dion","action":"status"}\n'
        self.assertEqual(s.enqueue(raw)['state'], 'queued')
        self.assertEqual(self.request.read_bytes(), raw)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['request.json'])

    def test_existing_request_preserved(self):
        self.request.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            s.enqueue(b'{"operation":"dion","action":"status"}')
        self.assertEqual(self.request.read_bytes(), b'original')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_busy_rejected(self):
        for name in ['dispatch.lock', 'processing.json']:
            p = self.root / name
            p.touch()
            with self.assertRaises(ValueError):
                s.enqueue(b'{"operation":"dion","action":"status"}')
            self.assertFalse(self.request.exists())
            p.unlink()

    def test_invalid_and_oversized_rejected(self):
        for raw in [b'', b'x' * 65537, b'not JSON', b'[]', b'{}',
                    b'{"operation":"shell","command":"anything"}',
                    b'{"operation":"mail","action":"send"}',
                    b'{"operation":"dion","action":"status","command":"anything"}']:
            with self.subTest(raw=raw[:80]):
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    s.enqueue(raw)
                self.assertFalse(self.request.exists())

    def test_cli_json_is_data(self):
        with patch.object(sys, 'argv', ['submit.py', '--json', '{"operation":"dion","action":"status"}']):
            s.main()
        self.assertTrue(self.request.is_file())

    def test_base64_cli_is_data(self):
        with patch.object(sys, 'argv', ['submit.py', '--json-base64', 'eyJvcGVyYXRpb24iOiJkaW9uIiwiYWN0aW9uIjoic3RhdHVzIn0=']):
            s.main()
        self.assertEqual(json.loads(self.request.read_bytes())['action'], 'status')

    def test_cli_rejects_extra_arguments(self):
        with patch.object(sys, 'argv', ['submit.py', '--json', '{}', 'extra']):
            with self.assertRaises(ValueError):
                s.main()
        self.assertFalse(self.request.exists())

    def test_unicode_title_is_data(self):
        raw = json.dumps({'operation': 'dion', 'action': 'start',
                          'title': '\u0412\u0441\u0442\u0440\u0435\u0447\u0430; $(never execute)'}).encode('utf-8')
        self.assertEqual(s.enqueue(raw)['action'], 'start')
        self.assertEqual(self.request.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
