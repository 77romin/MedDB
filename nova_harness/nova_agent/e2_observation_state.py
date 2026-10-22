"""Replace dual binary/keyword SAY interpretation with one observation ledger.

R3a retrieval, eligible question ordering, exam parser, ranking and end budgets
remain selected upstream components. Source contracts fail closed; original
files are never modified. Install after coverage_order and R3a retrieval.
"""
from copy import deepcopy
import json
from pathlib import Path
import types
from .observation_ledger import ObservationLedger

OLD='''        if care:
            care.observe(target, out, answer, st['turn'])
        if target:
            kb.asked.add(target)
            kb.turns.setdefault(target, st["turn"])
            if target in db.slots:
                kb.answers[target] = answer
            elif target in db.findings:
                kb.mark(target, read_answer(client, text, answer, db.findings[target]["ko"]), st["turn"], answer)
        kb.note_seen(answer, st["turn"])
'''
NEW='''        kb.observe_response(client, text, answer, target, st['turn'])
        if care:
            care.observe(target, out, answer, st['turn'])
            care.sync_observation(kb, target)
'''
INIT='''    transcript: list[str] = []
    care = None
'''
NEW_INIT='''    kb.observation_deadline = session.get('deadline')
    kb.observe_response(client, '', opening, None, 0)
    transcript: list[str] = []
    care = None
'''


def patched_source(source):
    if source.count(OLD)!=1 or source.count(INIT)!=1:raise ValueError('Unexpected E2 observation boundary')
    return source.replace(OLD,NEW).replace(INIT,NEW_INIT)


def install(events,ledgers=None):
    from examples import hybrid_agent as H,hybrid_comm,hybrid_care
    from meddb import coverage
    original_tracker=H.Tracker;original_writer=H.write_record
    original_consult=hybrid_care.base_consult;original_coverage=coverage.CareCoverage
    module=types.ModuleType('examples.hybrid_comm_observation_state');module.__file__=hybrid_comm.__file__
    exec(compile(patched_source(Path(module.__file__).read_text(encoding='utf-8')),module.__file__,'exec'),module.__dict__)

    class UnifiedTracker(original_tracker):
        def __init__(self,db,*args,**kwargs):
            self.observations=ObservationLedger(db)
            self.observation_deadline=None
            super().__init__(db,*args,**kwargs)
            # Existing raw history-slot handling stays upstream. This stage
            # unifies clinical finding assertions, not every numeric/history slot.
            if ledgers is not None:ledgers.append(self.observations)
        def note_seen(self,text,turn):
            # All patient SAY text enters observe_response exactly once; no
            # second alias-negation pass may overwrite that interpretation.
            return None
        def observe_response(self,client,question,answer,target,turn):
            self.observations.observe(client,question,answer,target,turn,self.observation_deadline)
            if target:
                self.asked.add(target);self.turns.setdefault(target,turn)
                if target in self.db.slots:self.answers[target]=answer
            view,conflicts=self.observations.view();clinical=set(self.observations.state.concepts)
            self.present[:]=[i for i in self.present if i not in clinical]
            self.absent[:]=[i for i in self.absent if i not in clinical]
            self.unknown.difference_update(clinical);self.conflicts.difference_update(clinical)
            self.conflicts.update(conflicts)
            for fid,value in view.items():
                if value=='+':self.present.append(fid)
                elif value=='-':self.absent.append(fid)
                else:self.unknown.add(fid)
                self.turns.setdefault(fid,turn)
                if fid in conflicts:self.conflict_turns[fid]=turn
            events.append({'event':'unified_observation_applied','turn':turn,
                           'patient_current_present':len([v for v in view.values() if v=='+']),
                           'patient_current_absent':len([v for v in view.values() if v=='-']),
                           'patient_current_unknown':len([v for v in view.values() if v=='?']),
                           'conflicts':len(conflicts),'facts':len(self.observations.state.facts),
                           'interpretation_failures':len(self.observations.failures)})

    class UnifiedCoverage(original_coverage):
        def sync_observation(self,kb,target):
            if target not in kb.observations.state.concepts:return
            status=kb.observations.answer_status.get(target,{}).get('status','unknown')
            row=getattr(self,'response_slots',{}).get(target)
            if not row or row['status']=='declined':return
            if status=='complete':row['status']='received'
            elif row['status']=='received':row['status']='partial'

    class RecordClient:
        def __init__(self,client,ledger):self.client=client;self.ledger=ledger
        def __getattr__(self,name):return getattr(self.client,name)
        def chat(self,messages,*,request_id=None,**kwargs):
            if request_id is not None:kwargs['request_id']=request_id
            if messages and str(messages[0].get('content','')).startswith('진료 기록만 근거로 초진 기록을 완성합니다.'):
                messages=deepcopy(messages)
                messages.append({'role':'user','content':'[구조화 관찰 원장: 모델 해석이며 원문 출처가 검증됨; 가족/과거/조건부/미확인을 현재 양음성으로 확대하지 않음]\n'+json.dumps(self.ledger.snapshot(),ensure_ascii=False)})
            return self.client.chat(messages,**kwargs)

    def writer(client,db,kb,*args,**kwargs):
        if hasattr(kb,'observations'):client=RecordClient(client,kb.observations)
        return original_writer(client,db,kb,*args,**kwargs)
    H.Tracker=UnifiedTracker;H.write_record=writer
    coverage.CareCoverage=UnifiedCoverage;hybrid_care.base_consult=module.consult
    return original_tracker,original_writer,original_consult,original_coverage


def restore(previous):
    from examples import hybrid_agent as H,hybrid_care
    from meddb import coverage
    H.Tracker,H.write_record,hybrid_care.base_consult,coverage.CareCoverage=previous
