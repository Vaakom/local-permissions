"""Verify narrow command matching. Does not execute checked operations."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PY = r'C:\AI\Tools\.dion-secretary\venv\Scripts\python.exe'
PS = r'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'


def patterns():
    result = []
    for script in ['run.py', 'submit.py']:
        path = str(HERE / script)
        launch = f"& '{PY}' -X utf8 -B '{path}'"
        result.extend([[PY, '-X', 'utf8', '-B', path], [PS, '-Command', launch]])
    return result


def source():
    return '# Narrow local request validation and authorized operations only.\n' + ''.join(
        'prefix_rule(pattern=' + json.dumps(p, ensure_ascii=False) + ', decision="allow")\n'
        for p in patterns())


def verify(rule_path):
    panel = Path('C:/AI/AI Native/.obsidian/plugins/codex-panel/data.json')
    codex = json.loads(panel.read_text(encoding='utf-8'))['codexPath']
    tests = [(p, True) for p in patterns()]
    tests += [([PY, '-c', 'print(1)'], False),
              ([PS, '-Command', 'Get-Content any-file'], False),
              ([PY, '-X', 'utf8', '-B', str(HERE / 'another.py')], False)]
    for p in patterns():
        if p[0] == PS:
            tests.append(([PS, '-Command', p[-1] + '; Write-Output extra'], False))
    env = dict(os.environ)
    home = Path('C:/AI/Tools/local-permissions/policy-check-home')
    home.mkdir(parents=True, exist_ok=True)
    env['CODEX_HOME'] = str(home)
    for command, expected in tests:
        r = subprocess.run([codex, 'execpolicy', 'check', '--rules', str(rule_path), '--', *command],
                           env=env, text=True, encoding='utf-8', capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr + r.stdout)
        result = json.loads(r.stdout)
        matched = result.get('decision') == 'allow'
        if matched != expected:
            raise AssertionError({'expected_allow': expected, 'command': command, 'result': result})
    print(json.dumps({'rules': str(rule_path), 'command_checks': len(tests), 'state': 'passed'}))


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--generate':
        (HERE / 'local-operations.rules').write_text(source(), encoding='utf-8')
    else:
        verify(Path(sys.argv[1]) if len(sys.argv) == 2 else HERE / 'local-operations.rules')
