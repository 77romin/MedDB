import unittest
from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from nova_agent.safety_obligations import ObligationLedger
from nova_agent.e2_safety_obligations import repair
from nova_agent import answered_questions as Q

class PartialTests(unittest.TestCase):
    def setUp(self):
        self.note={'P':{'education':'흉통 시 즉시 응급실 방문.'}}
        self.good={'source_field':'education','source_quote':'흉통 시 즉시 응급실 방문.','condition':'흉통 시','action':'즉시 응급실 방문','timing':'즉시','priority':'critical','applicability':'conditional','messages':['흉통 시 즉시 응급실 방문이 필요해요.']}
        self.ledger=ObligationLedger();self.ledger.update(self.note)
    def test_mixed_invalid_row_cannot_discard_independent_valid_row(self):
        bad=deepcopy(self.good);bad['messages']=['응급실 방문이 필요해요.']
        accepted,rejected=self.ledger.register_partial({'obligations':[bad,self.good]})
        self.assertEqual(len(accepted),1);self.assertEqual(len(rejected),1)
        self.assertEqual(len(self.ledger.audit([])['unresolved_ids']),1)
    def test_failed_repair_keeps_previously_accepted_obligation(self):
        _,rejected=self.ledger.register_partial({'obligations':[self.good,dict(self.good,messages=['즉시 응급실'])]})
        class Failing:
            def chat(self,*a,**kw):raise RuntimeError('offline')
        self.assertEqual(len(repair(Failing(),self.note,self.ledger,rejected)),1)
    def test_repair_cannot_change_original_condition_or_timing(self):
        _,rejected=self.ledger.register_partial({'obligations':[dict(self.good,messages=['응급실 방문이 필요해요.'])]})
        changed=dict(self.good,condition='',repair_index=0)
        class Fake:
            def chat(self,*a,**kw):return {'choices':[{'message':{'content':json.dumps({'obligations':[changed]},ensure_ascii=False)}}]}
        self.assertEqual(repair(Fake(),self.note,self.ledger,rejected),[])
    def test_one_bounded_repair_can_restore_a_complete_source_locked_group(self):
        _,rejected=self.ledger.register_partial({'obligations':[dict(self.good,messages=['응급실'])]})
        fixed=dict(self.good,repair_index=0)
        calls=[]
        class Fake:
            def chat(self,*a,**kw):calls.append(1);return {'choices':[{'message':{'content':json.dumps({'obligations':[fixed]},ensure_ascii=False)}}]}
        self.assertEqual(len(repair(Fake(),self.note,self.ledger,rejected)),1)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.ledger.versions[-1]['obligations'][0]['state'],'generated')

class QuestionTests(unittest.TestCase):
    def setUp(self):
        from meddb.coverage import CareCoverage
        self.C=CareCoverage;self.events=[];self.previous=Q.install(self.events)
        self.coverage=CareCoverage(None,None,None,None)
        self.kb=SimpleNamespace(conflicts=set(),exams_done=set())
    def tearDown(self):Q.restore(self.previous)
    def test_answered_question_blocked_without_new_patient_action(self):
        self.coverage.observe(None,'기분이 우울하거나 의욕이 없나요?','우울하진 않은데 의욕은 좀 없어요.',13)
        self.assertFalse(self.coverage.allow_action(self.kb,'SAY','기분이 우울하거나 의욕이 없나요?',None))
        self.assertTrue(self.events)
    def test_unclear_answer_and_conflicting_evidence_allow_clarification(self):
        self.coverage.observe(None,'무엇인가요?','잘 모르겠어요.',1)
        self.assertTrue(self.coverage.allow_action(self.kb,'SAY','무엇인가요?',None))
        self.coverage.observe(None,'증상이 있나요?','있어요.',2)
        self.kb.conflicts.add('symptom')
        self.assertFalse(self.coverage.allow_action(self.kb,'SAY','증상이 있나요?','symptom'))
        self.assertTrue(self.coverage.allow_action(self.kb,'SAY','앞서 답변의 다른 점을 설명해 주세요.',None))
    def test_required_candidates_also_filter_answered_exact_questions(self):
        from meddb.coverage import CareCoverage
        # Patch the saved original needed method through a fresh install.
        Q.restore(self.previous)
        with patch.object(CareCoverage,'needed',return_value=[{'type':'SAY','text':'증상이 있나요?','target':'symptom'}]):
            previous=Q.install(self.events)
            try:
                self.coverage.observe(None,'증상이 있나요?','없어요.',2)
                self.assertEqual(self.coverage.needed(self.kb),[])
            finally:Q.restore(previous)
        self.previous=Q.install(self.events)

class ClosingBudgetTests(unittest.TestCase):
    def test_valid_obligation_and_diagnosis_survive_without_clipping_plan_group(self):
        from examples import hybrid_comm as C,hybrid_agent as H
        from nova_agent import e2_safety_obligations as S3,e2_safety_delivery as S1
        from nova_agent.safety_trace import SafetyTimeline
        from datetime import datetime,timezone,timedelta
        note={'P':{'education':'흉통 시 즉시 응급실 방문. 상태를 알려 주세요.'}}
        row={'source_field':'education','source_quote':note['P']['education'],'condition':'흉통 시',
             'action':'즉시 응급실 방문','priority':'critical','applicability':'conditional',
             'messages':['흉통 시 즉시 응급실 방문이 필요해요.','상태를 알려 주세요.']}
        base=['원인을 확인할게요.','검사 계획이에요.','추가 검사도 설명할게요.']
        class Fake:
            def session(self):return {'turns_remaining':7,'deadline':(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()}
            def chat(self,*a,**kw):return {'choices':[{'message':{'content':json.dumps({'obligations':[row]},ensure_ascii=False)}}]}
        timeline=SafetyTimeline()
        with patch.object(C,'_closing_sentences',return_value=base),patch.object(H,'write_record'),patch.object(S1,'LAST_RUN',{'events':[{'event':'closing_proposed','messages':base,'groups':[[base[0]],base[1:]]}]}):
            original=S3.install(timeline,repair_invalid=True)
            try:
                actual=C._closing_sentences(Fake(),None,note,'가설','',True)
                self.assertEqual(actual,row['messages']+[base[0]])
                self.assertEqual(len(timeline.obligations.audit([])['unresolved_ids']),1)
            finally:S3.restore(original)
