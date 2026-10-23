"""Restore the optional official corpus locally; never include it in the submission ZIP."""
import hashlib
from pathlib import Path
import stat
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
URL='https://nova.snubhai.org/downloads/nova-guidelines-2026.zip'
SHA256='ef58c2f4369750af382f2706dcc1c9c7a85e3a93c261d880f7470d695eaf30d5'


def main():
    archive=ROOT/'downloads/nova-guidelines-2026.zip';archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        partial=archive.with_suffix('.partial')
        request=urllib.request.Request(URL,headers={'User-Agent':'nova-sdk/1.0.1'})
        with urllib.request.urlopen(request,timeout=60) as response,partial.open('wb') as stream:
            size=0
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                if size>250_000_000:raise ValueError('unexpected corpus archive size')
                stream.write(chunk)
        if hashlib.sha256(partial.read_bytes()).hexdigest()!=SHA256:raise ValueError('official corpus hash mismatch')
        partial.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:raise ValueError('existing corpus hash mismatch')
    root=(ROOT/'vendor/guidelines').resolve();root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist())>2_000_000_000:raise ValueError('expanded corpus too large')
        for info in z.infolist():
            path=(root/info.filename).resolve()
            if not path.is_relative_to(root) or stat.S_ISLNK(info.external_attr>>16):raise ValueError('unsafe corpus path')
        z.extractall(root)
    print('NOVA_GUIDELINES_DIR='+str(root/'guidelines'))

if __name__=='__main__':main()
