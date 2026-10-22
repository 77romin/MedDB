"""Synthetic diagnostic probes of the actual E2/experimental helper paths.

Not model benchmarks, full clinical sessions, or official scores. Known defects
are emitted as findings rather than hidden as expected passing assertions.
No production code or public answer scripts are changed/loaded.
"""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from meddb import MedDB,coverage
from examples import consult_skeleton as S,hybrid_agent as H,hybrid_comm as C
from nova_agent import response_state
from nova_agent.question_link import QuestionIndex
from nova_agent.safety_trace import SafetyTimeline,TimelineClient

class NoModel:
    def chat(self,*args,**kwargs):raise RuntimeError('Unexpected model dependency in deterministic probe')


def main():
    results=[]
    def check(id,layer,trigger,expected,actual,criterion,scope):
        results.append({'id':id,'layer':layer,'synthetic_input':trigger,'expected':expected,
                        'actual':actual,'status':'satisfied' if criterion(actual) else 'reproduced_defect',
                        'scope':scope})
    for id,question,answer,finding,expected in (
        ('E01','복통이 있나요?','설사는 없어요.','복통','?'),
        ('E02','지금 설사가 있나요?','예전에는 있었지만 지금은 없어요.','설사','-'),
        ('E03','설사가 있나요?','거의 없어요.','설사','?'),
        ('E04','설사가 있나요?','아니요, 없다는 뜻이 아니라 설사가 있어요.','설사','+')):
        actual=S.read_answer(NoModel(),question,answer,finding)
        check(id,'response_interpretation',{'question':question,'answer':answer,'finding':finding},
              expected,actual,lambda v,e=expected:v==e,'Existing E2 deterministic read_answer path; no Doctor call')
    db=MedDB.open()
    kb=H.Tracker(db,'weight_loss',30,'F','',{},'clinical','reviewed')
    kb.note_seen('어머니는 두근거림이 있어요.',turn=1)
    actual={'patient_present':list(kb.present),'patient_absent':list(kb.absent)}
    check('E05','subject_scope','어머니는 두근거림이 있어요.',
          'Must not assert palpitations in the patient',actual,
          lambda v:'palpitations' not in v['patient_present'],
          'Existing E2 Tracker.note_seen and MedDB aliases; not final SOAP')
    k=SimpleNamespace(conflicts=set(),asked={'sleep_hours'},present=set(),absent=set(),exams_done=set())
    base=coverage.CareCoverage(db,'insomnia',30,'F')
    base.observe('sleep_hours','몇 시간 주무세요?','잘 모르겠어요',2)
    baseline=any(a.get('target')=='sleep_hours' for a in base.needed(k))
    previous=response_state.install([])
    try:
        latest=coverage.CareCoverage(db,'insomnia',30,'F')
        latest.observe('sleep_hours','몇 시간 주무세요?','잘 모르겠어요',2)
        options=latest.needed(k)
        clarifies=any(a.get('target')=='sleep_hours' and a.get('_response_clarification') for a in options)
    finally:response_state.restore(previous)
    check('E06','coverage_completion',{'target':'sleep_hours','answer':'잘 모르겠어요'},
          'Original E2 should retain a clarification opportunity',baseline,lambda v:v,
          'Original coverage queue; raw answer remains but target is suppressed')
    check('E07','coverage_completion',{'target':'sleep_hours','answer':'잘 모르겠어요'},
          '47th response-state candidate retains bounded clarification',clarifies,lambda v:v,
          'Response-state overlay only; counterexample to claiming every layer still fails')
    idx=QuestionIndex(db,{},30,'F')
    for id,q,expected in (
        ('E08','기침이 2주 넘게 계속된 적 있나요?',None),
        ('E09','기침이 2주 넘게 계속되고 있나요?','chronic_cough'),
        ('E10','설사를 자주 하시나요?',None)):
        target,reason=idx.resolve(q)
        check(id,'question_scope',q,expected,{'target':target,'reason':reason},
              lambda v,e=expected:v['target']==e,'49th linker; no clinical answer inferred')
    timeline=SafetyTimeline()
    class Failed:
        def say(self,*args,**kwargs):raise RuntimeError('synthetic failure')
    try:TimelineClient(Failed(),timeline).say('알레르기가 있나요?')
    except RuntimeError:pass
    check('E11','action_acknowledgment','SAY request fails before acknowledged response',
          'No successful observation',len(timeline.speech),lambda v:v==0,
          'Passive TimelineClient helper; not a server retry/idempotency test')
    note=MedDB.empty_note()
    warning='흉통이나 호흡곤란이 새로 생기면 지체하지 말고 즉시 응급진료를 받으세요.'
    note['P']['education']=warning
    generated={'diagnosis':'가능성을 설명할게요.','plan':'검사 계획을 설명할게요.',
               'follow_up':'결과 확인을 위해 다시 오세요.','safety':warning,'concern':'걱정도 확인하겠습니다.'}
    with patch.object(H,'chat',lambda *a:json.dumps(generated,ensure_ascii=False)):
        actual=C._closing_sentences(NoModel(),db,note,'진단 미정','걱정돼요',comprehensive=True)
    check('E12','plan_to_speech',{'plan_warning':warning,'model_generated_safety':warning},
          'Condition and urgency should survive the speech preparation stage',actual,
          lambda v:all(any(term in s for s in v) for term in ('흉통','호흡곤란','즉시')),
          'Original R3a/E2 closing helper with injected synthetic output, not delivered speech or S3')
    paths=['vendor/meddb/examples/consult_skeleton.py','vendor/meddb/examples/hybrid_agent.py',
           'vendor/meddb/examples/hybrid_comm.py','vendor/meddb/meddb/coverage.py',
           'nova_agent/response_state.py','nova_agent/question_link.py','nova_agent/safety_trace.py']
    payload={'scope':'synthetic deterministic component diagnostics, not clinical/official performance',
             'scope_limits':['Expected behavior is specified by the author for these simple propositions, not an external clinical gold standard.',
                             'Original E2/R3a and optional overlays are labeled separately; do not pool failures across versions.',
                             'Original upstream defects are not newly introduced patch effects.',
                             'No conclusion that these cases caused the official safety/information scores.',
                             'Raw transcript remains available to final E2 SOAP generation; helper errors do not prove final SOAP necessarily wrong.'],
             'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
             'cases':results}
    out=ROOT/'reports/structural_edges_050.json';out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    for r in results:print(r['id'],r['status'],json.dumps(r['actual'],ensure_ascii=False))

if __name__=='__main__':main()
