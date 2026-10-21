"""Package S1 on the frozen R3a artifact; never include private timelines or keys."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]

def build():
    base=ROOT/'dist/submission_R3a_evidence_selection.zip'
    digest=hashlib.sha256(base.read_bytes()).hexdigest()
    if digest!='73570513ccda66c360ade7d73a6b415a56667748cc607d10442cdd57a3500dc8':raise ValueError('Frozen R3a required')
    with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
    run=files['run.py'].decode()
    old='''    original = install(db.rag_store)
    try:
        return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)'''
    new='''    from nova_agent.safety_trace import SafetyTimeline, TimelineClient, install as observe, restore as stop_observe
    from nova_agent import e2_safety_delivery
    original = install(db.rag_store)
    timeline = SafetyTimeline()
    old_safety = e2_safety_delivery.install(timeline)
    old_record = observe(timeline)
    tracked = e2_safety_delivery.wrap(TimelineClient(client, timeline), timeline)
    try:
        return meddb_consult(tracked, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        stop_observe(old_record)
        e2_safety_delivery.restore(old_safety)
        restore(original)
        import json, sys
        print(json.dumps({'event':'safety_delivery', 'records':len(timeline.records),
                          'successful_speech':len(timeline.speech), 'failed_actions':len(timeline.failures),
                          'events':[{'event':e['event'], 'field':e.get('field'),
                                     'status':e.get('status'), 'unresolved_fields':e.get('unresolved_fields')}
                                    for e in e2_safety_delivery.LAST_RUN['events']]}, ensure_ascii=False), file=sys.stderr)'''
    if run.count(old)!=1:raise ValueError('frozen consult contract changed')
    files['run.py']=run.replace(old,new).encode()
    for name in ('nova_agent/safety_trace.py','nova_agent/safety_delivery.py','nova_agent/e2_safety_delivery.py'):
        files[name]=(ROOT/name).read_bytes()
    out=ROOT/'dist/submission_S1_safety_delivery.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):z.writestr(name,files[name])
    assert out.stat().st_size<=50_000_000
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        subprocess.run([sys.executable,'-c',"import run; from nova_agent.safety_trace import SafetyTimeline,install as observe,restore as undo; from nova_agent import e2_rag_selection,e2_safety_delivery; db=run.prepare(); a=e2_rag_selection.install(db.rag_store); b=e2_safety_delivery.install(SafetyTimeline()); c=observe(SafetyTimeline()); undo(c); e2_safety_delivery.restore(b); e2_rag_selection.restore(a); db.rag_store.close(); print('S1 independent prepare/install/restore passed')"],cwd=tmp,check=True)
    manifest={'zip':str(out),'bytes':out.stat().st_size,'files':len(files),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
              'base_sha256':digest,'scope':'R3a search fixed; closing delivery, record continuity, actual education reconciliation; experimental, not uploaded'}
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    out.with_suffix('.zip.sha256').write_text(manifest['sha256']+'  '+out.name+'\n')
    print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':build()
