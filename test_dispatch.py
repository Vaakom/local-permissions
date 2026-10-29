import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dispatch', Path(__file__).with_name('run.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='C:/AI/Tools/local-permissions')
        root = Path(self.tmp.name)
        self.vault = root / 'vault'
        self.vault.mkdir()
        self.sessions = root / 'sessions'
        self.sessions.mkdir()
        self.notes = self.vault / 'meetings'
        self.notes.mkdir()
        self.patches = [patch.object(d, 'VAULT', self.vault), patch.object(d, 'SESSIONS', self.sessions),
                        patch.object(d, 'NOTES', self.notes), patch.object(d, 'DOCS', root / 'docs')]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def reject(self, req):
        with self.assertRaises((ValueError, TypeError, KeyError, FileNotFoundError)):
            d.build_plan(req)

    def test_title_is_one_argument(self):
        title = 'Meeting; $(bad) & other'
        kind, argv = d.build_plan({'operation': 'dion', 'action': 'start', 'title': title})
        self.assertEqual(kind, 'exec')
        self.assertEqual(argv[-1], title)
        self.assertEqual(argv[-2], '--title')

    def test_dion_setup_and_record_not_exposed(self):
        for action in ['setup-models', '_record', 'doctor', 'self-test']:
            self.reject({'operation': 'dion', 'action': action})

    def test_session_override_rejected(self):
        self.reject({'operation': 'dion', 'action': 'start', 'title': 'Meeting', 'session': str(self.sessions)})

    def test_process_external_path_rejected(self):
        self.reject({'operation': 'dion', 'action': 'process', 'session': str(self.vault)})

    def test_process_browser_and_codex_fixed(self):
        p = self.sessions / 'meeting'
        p.mkdir()
        _, argv = d.build_plan({'operation': 'dion', 'action': 'process', 'session': str(p)})
        self.assertEqual(argv[-4:], ['--minutes-provider', 'codex', '--speaker-mode', 'browser'])

    def test_mail_setup_send_delete_rejected(self):
        for action in ['setup', 'send', 'delete', 'move']:
            self.reject({'operation': 'mail', 'action': action})

    def test_mail_filters_are_argv(self):
        _, argv = d.build_plan({'operation': 'mail', 'action': 'search', 'text': 'x; Get-Content secret', 'all_folders': True})
        self.assertIn('x; Get-Content secret', argv)
        self.assertIn('--all-folders', argv)

    def test_mail_bad_fields_and_values(self):
        for req in [dict(action='read', uid='1;bad', folder='INBOX'),
                    dict(action='search', limit=101), dict(action='search', since='yesterday'),
                    dict(action='search', command='send')]:
            self.reject({'operation': 'mail', **req})

    def test_export_only_output(self):
        self.reject({'operation': 'mail', 'action': 'export', 'sender': 'a@b', 'subjects': ['x'],
                     'destination': str(self.vault / 'private' / 'mail')})
        _, argv = d.build_plan({'operation': 'mail', 'action': 'export', 'sender': 'a@b', 'subjects': ['x'],
                                'destination': str(self.vault / 'output' / 'mail')})
        self.assertIn('--destination', argv)

    def test_private_hidden_and_executable_rejected(self):
        for rel in ['private/note.md', '.obsidian/app.json', 'file.exe', 'file.ps1', 'file.cmd', 'file.lnk']:
            p = self.vault / rel
            p.parent.mkdir(exist_ok=True)
            p.touch()
            self.reject({'operation': 'open', 'target': str(p)})

    def test_url_protocol_restrictions(self):
        for url in ['file:///C:/Windows/a.exe', 'javascript:alert(1)', 'obsidian://anything',
                    'https://user:password@example.com', 'https://example.com\nattack']:
            self.reject({'operation': 'open', 'target': url})
        self.assertEqual(d.build_plan({'operation': 'open', 'target': 'https://example.com/a'}),
                         ('open', 'https://example.com/a'))

    def test_obsidian_anchor_encoded(self):
        p = self.vault / 'note.md'
        p.touch()
        kind, uri = d.build_plan({'operation': 'open', 'target': str(p), 'anchor': '^t-00-35-52-2'})
        self.assertEqual(kind, 'open')
        self.assertIn('%23%5Et-00-35-52-2', uri)
        self.reject({'operation': 'open', 'target': str(p), 'anchor': '^x&file=bad'})

    def test_external_doc_rejected(self):
        p = Path(self.tmp.name) / 'outside.pdf'
        p.touch()
        self.reject({'operation': 'open', 'target': str(p)})

    def test_fixed_audit_only(self):
        self.reject({'operation': 'audit', 'check': 'run-anything'})
        self.reject({'operation': 'audit', 'check': 'vault', 'args': ['--bad']})
        self.assertIn('audit.py', d.build_plan({'operation': 'audit', 'check': 'vault'})[1][4])

    def test_symlink_escape_rejected(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'note.md').touch()
        link = self.vault / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable on this Windows account')
        self.reject({'operation': 'open', 'target': str(link / 'note.md')})


if __name__ == '__main__':
    unittest.main()
