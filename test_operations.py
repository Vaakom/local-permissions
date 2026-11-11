import unittest
import contextlib
import io
from unittest.mock import patch, Mock
import operations as o
import run


class OperationsTests(unittest.TestCase):
    def test_dispatch_fixed_operations(self):
        for req in [{'operation':'tests','suite':'permissions'},
                    {'operation':'diagnostic','component':'syncthing'},
                    {'operation':'github','action':'ci','repo':'skills'},
                    {'operation':'link','url':'https://example.com/'}]:
            kind, argv = run.build_plan(req)
            self.assertEqual(kind, 'exec')
            self.assertEqual(argv[4], str(o.Path(o.__file__).resolve()))

    def test_unknown_fields_and_selectors_rejected(self):
        for req in [{'operation':'tests','suite':'anything'},
                    {'operation':'tests','suite':'permissions','args':['--bad']},
                    {'operation':'diagnostic','component':'syncthing','method':'POST'},
                    {'operation':'github','action':'push','repo':'skills'},
                    {'operation':'github','action':'ci','repo':'other'},
                    {'operation':'github','action':'auth','repo':'skills'}]:
            with self.assertRaises(ValueError):
                run.build_plan(req)

    def test_private_network_and_credentials_rejected(self):
        for url in ['file:///x','https://a:b@example.com','http://localhost:8384/', 'https://example.com/\nsecret']:
            with self.assertRaises(ValueError):
                o.public_url(url, resolve=False)
        with patch.object(o.socket, 'getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',80))]):
            with self.assertRaises(ValueError):
                o.public_url('http://example.com')

    def test_redirect_to_private_blocked(self):
        response = Mock(status=302)
        response.getheader.return_value = 'http://localhost/'
        conn = Mock()
        conn.getresponse.return_value = response
        with patch.object(o.http.client, 'HTTPConnection', return_value=conn), patch.object(o.socket, 'getaddrinfo', side_effect=[[(2,1,6,'',('93.184.216.34',80))],[(2,1,6,'',('127.0.0.1',80))]]):
            with self.assertRaises(ValueError):
                o.check_link('http://example.com')
        self.assertEqual(conn.request.call_count, 1)

    def test_test_suite_does_not_accept_shell_arguments(self):
        with patch.object(o.subprocess, 'run', return_value=Mock(returncode=0)) as call:
            self.assertEqual(o.execute({'operation':'tests','suite':'archive'}),0)
            self.assertFalse(call.call_args.kwargs['shell'])
            self.assertIn('test_archive', call.call_args.args[0])

    def test_archive_outputs_only_status_metadata(self):
        data = {'checked_utc':'now', 'pid':1, 'matched':2, 'changed':0,
                'errors':['sensitive path'], 'secret':'never print'}
        with patch.object(o, 'load_json', return_value=data):
            result = o.diagnostic('archive')
        self.assertEqual(result['errors'], 1)
        self.assertNotIn('sensitive', str(result))
        self.assertNotIn('secret', result)

    def test_syncthing_uses_only_fixed_get_endpoints(self):
        config = o.ET.ElementTree(o.ET.fromstring('<configuration><gui><apikey>fixture-key</apikey><address>127.0.0.1:8384</address></gui></configuration>'))
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.side_effect = [b'{"state":"idle","errors":0}', b'{"ignore":["example"]}']
        with patch.object(o.ET, 'parse', return_value=config), patch.object(o.http.client, 'HTTPConnection', return_value=connection):
            result = o.diagnostic('syncthing')
        requests = connection.request.call_args_list
        self.assertEqual(len(requests), 2)
        self.assertEqual([c.args[0] for c in requests], ['GET', 'GET'])
        self.assertTrue(requests[0].args[1].startswith('/rest/db/status?folder='))
        self.assertTrue(requests[1].args[1].startswith('/rest/db/ignores?folder='))
        self.assertNotIn('fixture-key', str(result))

    def test_github_uses_only_fixed_read_commands(self):
        with patch.object(o.subprocess, 'run', return_value=Mock(returncode=0)) as call:
            o.execute({'operation':'github','action':'refs','repo':'permissions'})
            argv = call.call_args.args[0]
            self.assertEqual(argv[1:], ['api','repos/Vaakom/local-permissions/git/ref/heads/main','--jq','.object.sha'])
        output = io.StringIO()
        with patch.object(o.subprocess, 'run', return_value=Mock(returncode=1, stdout='do-not-echo')):
            with contextlib.redirect_stdout(output):
                o.execute({'operation':'github','action':'auth'})
        self.assertNotIn('do-not-echo', output.getvalue())


if __name__ == '__main__':
    unittest.main()
