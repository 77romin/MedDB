"""Explicit allowlist overlay on frozen R3a; no credentials, logs or dev docs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]
MODULES=('nova_agent/safety_trace.py','nova_agent/response_state.py','nova_agent/coverage_order.py',
         'nova_agent/state.py','nova_agent/observation_ledger.py','nova_agent/e2_observation_state.py',
         'nova_agent/model_question_policy.py')
OLD="""    original = install(db.rag_store)
    try:
        return meddb_consult(client, db, fallback=baseline_consult, knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        restore(original)"""
NEW="""    from nova_agent import response_state, coverage_order, e2_observation_state, model_question_policy
    from nova_agent.safety_trace import SafetyTimeline, TimelineClient, install as observe, restore as unobserve
    original = install(db.rag_store)
    events = []
    ledgers = []
    old_response = response_state.install(events)
    old_order = coverage_order.install(events)
    old_unified = e2_observation_state.install(events, ledgers)
    old_policy = model_question_policy.install(events)
    timeline = SafetyTimeline()
    old_record = observe(timeline)
    try:
        return meddb_consult(TimelineClient(client, timeline), db, fallback=baseline_consult,
                            knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        unobserve(old_record)
        model_question_policy.restore(old_policy)
        e2_observation_state.restore(old_unified)
        coverage_order.restore(old_order)
        response_state.restore(old_response)
        restore(original)"""


def build():
    base=ROOT/'dist/submission_R3a_evidence_selection.zip'
    digest=hashlib.sha256(base.read_bytes()).hexdigest()
    if digest!='73570513ccda66c360ade7d73a6b415a56667748cc607d10442cdd57a3500dc8':raise ValueError('Frozen R3a required')
    with zipfile.ZipFile(base) as z:files={n:z.read(n) for n in z.namelist()}
    run=files['run.py'].decode()
    if run.count(OLD)!=1:raise ValueError('Frozen dispatch contract changed')
    files['run.py']=run.replace(OLD,NEW).encode()
    for name in MODULES:files[name]=(ROOT/name).read_bytes()
    for name in files:
        parts=Path(name).parts
        if name.startswith('/') or '..' in parts or any(p in ('.env','results','vendor','__pycache__','DECISIONS.md','AGENTS.md','REPOSITORY_HANDOFF.md') for p in parts):
            raise ValueError('Disallowed member')
        if name.endswith('.py'):compile(files[name],name,'exec')
    out=ROOT/'dist/submission_Q1_model_questions.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info=zipfile.ZipInfo(name,date_time=(2026,10,23,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,files[name])
    if out.stat().st_size>50_000_000:raise ValueError('ZIP size limit exceeded')
    with zipfile.ZipFile(out) as z:assert z.testzip() is None
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:z.extractall(tmp)
        check="""import run
from examples import hybrid_agent as H, hybrid_care
from nova_agent import model_question_policy
saved=hybrid_care.base_consult
writer=H.write_record
seen=[]
def fake(client, db, **kwargs):
    assert '_model_question_choose' in hybrid_care.base_consult.__globals__
    assert hasattr(H.Tracker, 'observe_response')
    seen.append(True)
    return 'dispatch-ok'
run.meddb_consult=fake
db=run.prepare()
assert run.consult(object(), db)=='dispatch-ok'
assert seen==[True]
assert hybrid_care.base_consult is saved
assert H.write_record is writer
db.rag_store.close()
print('independent ZIP prepare/dispatch/restore passed')
"""
        subprocess.run([sys.executable,'-c',check],cwd=tmp,check=True)
    manifest={'zip':out.name,'bytes':out.stat().st_size,'files':len(files),
              'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'base_sha256':digest,
              'scope':'User-requested Q1 sample comparison; model questions on R3a observation state; not uploaded; official improvement unconfirmed',
              'runtime_sha256':{n:hashlib.sha256(files[n]).hexdigest() for n in MODULES}}
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    out.with_suffix('.zip.sha256').write_text(manifest['sha256']+'  '+out.name+'\n')
    print(json.dumps(manifest,ensure_ascii=False));return manifest

if __name__=='__main__':build()
