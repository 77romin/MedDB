"""Restore ignored official packages using pinned archive checksums."""
import hashlib
import json
from pathlib import Path
import stat
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    for source in json.loads((ROOT/'vendor_sources.json').read_text(encoding='utf-8')):
        archive = ROOT/'downloads'/(source['name']+'.zip')
        archive.parent.mkdir(exist_ok=True)
        if not archive.exists():
            req = urllib.request.Request(source['url'], headers={'User-Agent': 'nova-sdk/1.0.1'})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read(20_000_001)
            if len(data) > 20_000_000:
                raise ValueError('unexpected archive size')
        else:
            data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != source['sha256']:
            raise ValueError('official archive changed; inspect and update vendor_sources.json deliberately')
        archive.write_bytes(data)
        target = (ROOT/'vendor'/source['name']).resolve()
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            if sum(m.file_size for m in z.infolist()) > 100_000_000:
                raise ValueError('unexpected expanded size')
            for member in z.infolist():
                path = (target/member.filename).resolve()
                if target not in path.parents and path != target:
                    raise ValueError('unsafe archive path')
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError('archive symlink')
            z.extractall(target)
        print('Ready:', source['name'])


if __name__ == '__main__':
    main()
