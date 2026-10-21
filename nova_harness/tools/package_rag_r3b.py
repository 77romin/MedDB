"""Query-role-only change on the user-tested, frozen R3a artifact."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build(out=None):
    out=Path(out or ROOT/'dist/submission_R3b_query_planning.zip')
    base=ROOT/'dist/submission_R3a_evidence_selection.zip'
    if hashlib.sha256(base.read_bytes()).hexdigest()!='73570513ccda66c360ade7d73a6b415a56667748cc607d10442cdd57a3500dc8':
        raise ValueError('frozen R3a artifact required')
    with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
    run=files['run.py'].decode()
    old='from nova_agent.e2_rag_selection import install, restore'
    if run.count(old)!=1:raise ValueError('R3a wrapper contract changed')
    run=run.replace(old,'from nova_agent.e2_rag_query import install, restore')
    old="        print(json.dumps({'event':'rag_selection','audit':e2_rag_selection.LAST_RUN}, ensure_ascii=False), file=sys.stderr)"
    if run.count(old)!=1:raise ValueError('R3a audit contract changed')
    run=run.replace(old,old+"\n        from nova_agent import e2_rag_query\n        print(json.dumps({'event':'rag_query','audit':e2_rag_query.LAST_RUN}, ensure_ascii=False), file=sys.stderr)")
    files['run.py']=run.encode()
    for n in ('nova_agent/rag_query.py','nova_agent/e2_rag_query.py'):files[n]=(ROOT/n).read_bytes()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):z.writestr(n,files[n])
    if out.stat().st_size>50_000_000:raise ValueError('ZIP too large')
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        subprocess.run([sys.executable,'-c','import run; from nova_agent.e2_rag_query import install,restore; db=run.prepare(); old=install(db.rag_store); restore(old); db.rag_store.close(); print("R3b prepare and overlay OK")'],cwd=tmp,check=True)
    result={'zip':str(out),'bytes':out.stat().st_size,'files':len(files),
            'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
            'scope':'R3a frozen selector, retrieval, index and generation; query planning only'}
    out.with_suffix('.manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return result


if __name__=='__main__':build()
