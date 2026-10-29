"""Install only the reviewed rules file; preserve other Codex configuration."""
import datetime
import hashlib
from pathlib import Path
import shutil
from verify_rules import verify

HERE = Path(__file__).resolve().parent


def main():
    source = HERE / 'local-operations.rules'
    target = Path.home() / '.codex/rules/local-operations.rules'
    backup_root = Path('C:/AI/Tools/local-permissions/backups')
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = backup_root / ('local-operations-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.rules')
        shutil.copy2(target, backup)
    pending = target.with_suffix('.rules.pending')
    shutil.copy2(source, pending)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(pending.read_bytes()).digest():
        raise RuntimeError('Rule copy hash mismatch')
    pending.replace(target)
    verify(target)
    print('Installed:', target)


if __name__ == '__main__':
    main()
