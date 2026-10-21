"""Package generation role on the frozen R3b artifact, not on a rebuilt ZIP."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build(out=None):
    out=Path(out or ROOT/'dist/submission_R3c_grounded_generation.zip')
    base=ROOT/'dist/submission_R3b_query_planning.zip'
    if hashlib.sha256(base.read_bytes()).hexdigest()!='a7d0339a6ff8ffa28f2cb5e64194e9527d11aa21b008209d61ceed23a4178083':
        raise ValueError('frozen R3b artifact required')
    with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
    run=files['run.py'].decode();old='from nova_agent.e2_rag_query import install, restore'
    if run.count(old)!=1:raise ValueError('R3b contract changed')
    run=run.replace(old,'from nova_agent.e2_rag_generation import install, restore')
    old="        print(json.dumps({'event':'rag_query','audit':e2_rag_query.LAST_RUN}, ensure_ascii=False), file=sys.stderr)"
    if run.count(old)!=1:raise ValueError('R3b audit contract changed')
    run=run.replace(old,old+"\n        from nova_agent import e2_rag_generation\n        print(json.dumps({'event':'rag_generation','audit':e2_rag_generation.LAST_RUN}, ensure_ascii=False), file=sys.stderr)")
    files['run.py']=run.encode()
    for n in ('nova_agent/rag_generation.py','nova_agent/e2_rag_generation.py'):files[n]=(ROOT/n).read_bytes()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):z.writestr(n,files[n])
    if out.stat().st_size>50_000_000:raise ValueError('ZIP too large')
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        subprocess.run([sys.executable,'-c','import run; from nova_agent.e2_rag_generation import install,restore; db=run.prepare(); old=install(db.rag_store); restore(old); db.rag_store.close(); print("R3c prepare and overlay OK")'],cwd=tmp,check=True)
    result={'zip':str(out),'bytes':out.stat().st_size,'files':len(files),
            'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
            'scope':'R3b query and selector frozen; generation role only; no extra Doctor calls'}
    out.with_suffix('.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':build()
