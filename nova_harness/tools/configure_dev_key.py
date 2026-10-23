"""Local interactive credential setup; never prints or accepts keys as arguments."""
from getpass import getpass
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / '.env'
    if target.is_symlink():
        raise SystemExit('Refusing a symlink .env; use a regular local file.')
    key = getpass('NOVA development key (hidden input): ').strip()
    if not key or any(c.isspace() for c in key) or any(c in key for c in ('"', "'", '#')):
        raise SystemExit('Empty or malformed input; existing configuration preserved.')
    lines = target.read_text(encoding='utf-8').splitlines() if target.exists() else []
    lines = [line for line in lines if not re.match(r'^\s*(?:export\s+)?NOVA_DEV_KEY\s*=', line)]
    lines.append('NOVA_DEV_KEY=' + key)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=ROOT, prefix='.env.key-', delete=False) as f:
            temporary = Path(f.name)
            os.chmod(f.name, 0o600)
            f.write('\n'.join(lines) + '\n')
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():temporary.unlink()
    print('Saved locally. No key was printed. Tell Codex: key setup complete.')

if __name__ == '__main__':
    try:main()
    except (KeyboardInterrupt, EOFError):raise SystemExit('Cancelled; existing configuration preserved.')
