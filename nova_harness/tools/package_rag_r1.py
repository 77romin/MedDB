"""Explicit allowlist R1 package on the frozen E2 baseline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(out=None):
    out = Path(out or ROOT/'dist/submission_R1_rag_baseline.zip')
    base = ROOT/'dist/submission_meddb_E2_reference.zip'
    with zipfile.ZipFile(base) as z:
        files = {name: z.read(name) for name in z.namelist()}
    run = files['run.py'].decode()
    old = "    return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')"
    if run.count(old) != 1:
        raise ValueError('upstream contract changed')
    new = '''    from nova_agent.e2_rag import install, restore
    original = install(knowledge.rag_store)
    try:
        return meddb_consult(client, knowledge.db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)
        import json, sys
        from nova_agent import e2_rag
        print(json.dumps({'event':'rag_record_context','audit':e2_rag.LAST_RUN}, ensure_ascii=False), file=sys.stderr)'''
    # Baseline prepare returns MedDB; consult argument is checked before mutation.
    import ast
    tree = ast.parse(run)
    consult = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'consult')
    print('consult args:', [a.arg for a in consult.args.args])
    # use existing db variable; wrapper exposes the original DB through __getattr__.
    new = new.replace('knowledge.rag_store', 'db.rag_store').replace('knowledge.db', 'db')
    run = run.replace(old, new)
    # Wrap the original prepare without modifying its body or contract.
    prepare_wrapper = '''
_base_prepare = prepare
def prepare():
    from pathlib import Path
    from nova_agent.rag import VectorStore
    db = _base_prepare()
    db.rag_store = VectorStore(Path(__file__).resolve().parent/'rag/index.sqlite')
    return db
'''
    run = run.replace("if __name__ == '__main__':", prepare_wrapper+"\nif __name__ == '__main__':")
    files['run.py'] = run.encode()
    files['requirements.txt'] = b'numpy==2.2.6\n'
    for name in ('nova_agent/__init__.py', 'nova_agent/rag.py', 'nova_agent/e2_rag.py'):
        files[name] = (ROOT/name).read_bytes()
    files['rag/index.sqlite'] = (ROOT/'dist/rag/index.sqlite').read_bytes()
    if any(n.startswith(('.env','results/','tests/','tools/','vendor/')) for n in files):
        raise ValueError('forbidden member')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            z.writestr(name, files[name])
    if out.stat().st_size > 50_000_000:
        raise ValueError('package exceeds 50MB')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:
            z.extractall(tmp)
        subprocess.run([sys.executable, '-c',
                        'import run; db=run.prepare(); print(db.rag_store.meta); db.rag_store.close()'],
                       cwd=tmp, check=True)
    result = {'zip': str(out), 'bytes': out.stat().st_size, 'files': len(files),
              'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
              'base_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
              'scope': 'E2 + LSA guideline RAG at record generation only; no active convergence'}
    out.with_suffix('.manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    build()
