"""Package LangGraph on the frozen R3c artifact, not on a rebuilt ZIP."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build(out=None):
    out=Path(out or ROOT/'dist/submission_R4_langgraph_final.zip')
    base=ROOT/'dist/submission_R3c_grounded_generation.zip'
    if hashlib.sha256(base.read_bytes()).hexdigest()!='f73dfc029f9600a9d5da381af4510a4ef84afc2d9644d10700a0fa6f05f8f90c':
        raise ValueError('frozen R3c artifact required')
    with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
    run=files['run.py'].decode()
    old='from nova_agent.e2_rag_generation import install, restore'
    if run.count(old)!=1:raise ValueError('R3c import contract changed')
    run=run.replace(old,'from nova_agent.rag_graph import install, restore')
    old="        print(json.dumps({'event':'rag_generation','audit':e2_rag_generation.LAST_RUN}, ensure_ascii=False), file=sys.stderr)"
    if run.count(old)!=1:raise ValueError('R3c audit contract changed')
    run=run.replace(old,old+"\n        from nova_agent import rag_graph\n        print(json.dumps({'event':'rag_graph','audit':rag_graph.LAST_RUN}, ensure_ascii=False), file=sys.stderr)")
    old="    db.rag_store = VectorStore(Path(__file__).resolve().parent/'rag/index.sqlite')"
    if run.count(old)!=1:raise ValueError('prepare contract changed')
    run=run.replace(old,old+"\n    from nova_agent.rag_graph import validate_runtime\n    validate_runtime()")
    files['run.py']=run.encode()
    files['nova_agent/rag_graph.py']=(ROOT/'nova_agent/rag_graph.py').read_bytes()
    files['requirements.txt']=(ROOT/'tools/requirements-rag-r4.txt').read_bytes()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):z.writestr(n,files[n])
    if out.stat().st_size>50_000_000:raise ValueError('ZIP too large')
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        subprocess.run([sys.executable,'-c','import run; from nova_agent.rag_graph import install,restore; db=run.prepare(); old=install(db.rag_store); restore(old); db.rag_store.close(); print("R4 prepare and graph overlay OK")'],cwd=tmp,check=True)
    result={'zip':str(out),'bytes':out.stat().st_size,'files':len(files),
            'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
            'scope':'R3c clinical operations frozen; local LangGraph orchestration; no extra Doctor calls'}
    out.with_suffix('.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':build()
