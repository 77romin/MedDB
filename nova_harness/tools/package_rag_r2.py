"""R2 changes only the retrieval implementation in the frozen R1 artifact."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(out=None):
    out = Path(out or ROOT/'dist/submission_R2_retrieval.zip')
    base = ROOT/'dist/submission_R1_rag_baseline.zip'
    if hashlib.sha256(base.read_bytes()).hexdigest() != 'd70e4e9c84afa6e47d79c0e3ac47ae0534f987f64bd6843a9b73d3b03f8b6a28':
        raise ValueError('R1 baseline must be the frozen user-tested artifact')
    with zipfile.ZipFile(base) as z:
        files = {name:z.read(name) for name in z.namelist()}
    run = files['run.py'].decode()
    old = 'from nova_agent.rag import VectorStore'
    if run.count(old) != 1:
        raise ValueError('unexpected R1 contract')
    files['run.py'] = run.replace(old, 'from nova_agent.rag_retrieval import VectorStore').encode()
    name = 'nova_agent/rag_retrieval.py'
    files[name] = (ROOT/name).read_bytes()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            z.writestr(name, files[name])
    if out.stat().st_size > 50_000_000:
        raise ValueError('package exceeds 50MB')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:
            z.extractall(tmp)
        subprocess.run([sys.executable,'-c',
                        'import run; db=run.prepare(); print(db.rag_store.meta); db.rag_store.close()'],cwd=tmp,check=True)
    result = {'zip':str(out),'bytes':out.stat().st_size,'files':len(files),
              'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
              'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
              'changed':['run.py','nova_agent/rag_retrieval.py'],
              'scope':'R1 encoder, index, generation prompt unchanged; R2 retrieval only'}
    out.with_suffix('.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__ == '__main__':
    build()
