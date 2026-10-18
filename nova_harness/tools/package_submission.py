"""Explicit allowlist packaging: cannot include .env, results, samples, or answer keys."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(destination=None):
    paths = [ROOT/'run.py', ROOT/'nova_sdk.py', ROOT/'requirements.txt',
             *sorted((ROOT/'nova_agent').glob('*.py')), *sorted((ROOT/'nova_agent').glob('*.json')),
             *sorted((ROOT/'third_party/meddb').glob('*'))]
    assert len(paths) <= 5000
    assert sum(p.stat().st_size for p in paths) <= 500_000_000
    dest = Path(destination) if destination is not None else ROOT/'dist/submission.zip'
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p.is_symlink():
                raise ValueError('symlink in submission allowlist')
            z.write(p, p.relative_to(ROOT))
    if dest.stat().st_size > 50_000_000:
        raise ValueError('submission exceeds ZIP limit')
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:
            raise ValueError('corrupt ZIP')
    print(json.dumps({'path': str(dest), 'bytes': dest.stat().st_size,
                      'files': len(paths), 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}, indent=2))
    return dest


if __name__ == '__main__':
    build()
