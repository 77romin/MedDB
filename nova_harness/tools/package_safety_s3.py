"""Package S3 on the frozen R3a artifact; never include private timelines or keys."""
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
    from nova_agent import e2_safety_delivery, e2_safety_obligations, answered_questions
    original = install(db.rag_store)
    timeline = SafetyTimeline()
    old_safety = e2_safety_delivery.install(timeline)
    old_obligations = e2_safety_obligations.install(timeline, repair_invalid=True)
    old_questions = answered_questions.install(timeline.obligations.events)
    tracked = e2_safety_obligations.wrap(TimelineClient(client, timeline), timeline)
    old_record = observe(timeline)
    try:
        return meddb_consult(tracked, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        stop_observe(old_record)
        answered_questions.restore(old_questions)
        e2_safety_obligations.restore(old_obligations)
        e2_safety_delivery.restore(old_safety)
        restore(original)
        import json, sys
        print(json.dumps({'event':'safety_obligations', 'records':len(timeline.records),
                          'successful_speech':len(timeline.speech), 'failed_actions':len(timeline.failures)}, ensure_ascii=False), file=sys.stderr)'''
    if run.count(old)!=1:raise ValueError('frozen consult contract changed')
    files['run.py']=run.replace(old,new).encode()
    for name in ('nova_agent/safety_trace.py','nova_agent/safety_delivery.py','nova_agent/e2_safety_delivery.py','nova_agent/safety_obligations.py','nova_agent/e2_safety_obligations.py','nova_agent/answered_questions.py'):
        files[name]=(ROOT/name).read_bytes()
    out=ROOT/'dist/submission_S3_safety_obligations.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):z.writestr(name,files[name])
    assert out.stat().st_size<=50_000_000
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        check = """import run
from examples import hybrid_agent as H
from nova_agent import e2_safety_obligations as obligations
original_record = H.write_record
original_install = obligations.install
flags=[]
def checked_install(timeline, repair_invalid=False):
    flags.append(repair_invalid)
    return original_install(timeline, repair_invalid=repair_invalid)
obligations.install=checked_install
def fake_consult(client, db, **kwargs):
    assert client.say.__kwdefaults__['request_id'] is None
    return 'dispatch-ok'
run.meddb_consult=fake_consult
db=run.prepare()
assert run.consult(object(), db)=='dispatch-ok'
assert flags==[True]
assert H.write_record is original_record
db.rag_store.close()
print('S3 independent prepare/dispatch/restore passed')
"""
        subprocess.run([sys.executable,'-c',check],cwd=tmp,check=True)
    manifest={'zip':out.name,'bytes':out.stat().st_size,'files':len(files),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
              'base_sha256':digest,'scope':'Diagnostic sample candidate; R3a retrieval with S3 obligations and answered-question guard; not officially uploaded', 'runtime_sha256':{name:hashlib.sha256(files[name]).hexdigest() for name in files if name in ('nova_agent/safety_trace.py','nova_agent/safety_delivery.py','nova_agent/e2_safety_delivery.py','nova_agent/safety_obligations.py','nova_agent/e2_safety_obligations.py','nova_agent/answered_questions.py')}}
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    out.with_suffix('.zip.sha256').write_text(manifest['sha256']+'  '+out.name+'\n')
    print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':build()
