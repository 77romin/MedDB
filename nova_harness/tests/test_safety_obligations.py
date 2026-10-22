import unittest
from copy import deepcopy
from nova_agent.safety_obligations import ObligationLedger, complete_message
from nova_agent.safety_trace import SafetyTimeline, TimelineClient

class ObligationTests(unittest.TestCase):
    def setUp(self):
        self.note={'S':{'history':'환자 진술'},'O':{},'A':{},'P':{'education':'흉통 시 응급실 방문. 운전 금지 안내 완료.', 'follow_up':'3일 후 재진'}}
        self.row={'source_field':'education','source_quote':'흉통 시 응급실 방문.', 'condition':'흉통 시','action':'응급실 방문', 'priority':'critical','applicability':'conditional','messages':['흉통 시 응급실 방문이 필요해요.']}
        self.ledger=ObligationLedger();self.ledger.update(self.note)
    def test_generated_is_not_delivered(self):
        self.ledger.register({'obligations':[self.row]})
        self.assertEqual(len(self.ledger.audit([])['unresolved_ids']),1)
    def test_only_complete_successful_group_is_credited(self):
        self.ledger.register({'obligations':[self.row]})
        speech=[{'index':0,'record_count':1,'content':self.row['messages'][0]}]
        self.assertEqual(self.ledger.audit(speech)['unresolved_ids'],[])
        speech[0]['content']='힘들면 진료받으세요.'
        self.assertEqual(len(self.ledger.audit(speech)['unresolved_ids']),1)
    def test_negation_condition_new_number_and_fragment_rejected(self):
        for key,value in [('condition','없는 조건'),('messages',['즉시 응급진료']),('messages',['흉통 시 응급실 방문을 2번 하세요.']),('messages',['응급실 방문이 필요해요.'])]:
            row=deepcopy(self.row);row[key]=value
            with self.assertRaises(ValueError):self.ledger.register({'obligations':[row]})
    def test_changed_plan_does_not_inherit_old_delivery(self):
        self.ledger.register({'obligations':[self.row]})
        note=deepcopy(self.note);note['P']['follow_up']='1일 후 재진'
        self.ledger.update(note);self.ledger.register({'obligations':[self.row]})
        audit=self.ledger.audit([{'index':0,'record_count':1,'content':self.row['messages'][0]}])
        self.assertEqual(len(audit['unresolved_ids']),1)
        self.assertTrue(audit['plan_changed_after_speech'])
    def test_render_preserves_facts_and_attributes_unverified_plan(self):
        before=deepcopy(self.note)
        out=self.ledger.render(self.note,[])
        self.assertEqual(self.note,before);self.assertEqual(out['S'],before['S'])
        self.assertIn('수행 여부 미확인',out['P']['education'])
        self.assertIn('확인된 전달 없음',out['P']['education'])
    def test_failed_say_cannot_become_performed(self):
        class Failing:
            def say(self,*a,**kw):raise ValueError('failed')
        t=SafetyTimeline();client=TimelineClient(Failing(),t)
        with self.assertRaises(ValueError):client.say('안내해요.',request_id='retry-id')
        self.assertEqual(t.speech,[])
    def test_request_identity_and_no_inferred_understanding(self):
        class OK:
            def say(self,*a,**kw):return {'content':'네'}
        t=SafetyTimeline();TimelineClient(OK(),t).say('안내해요.',request_id='stable')
        self.assertEqual(t.speech[0]['request_id'],'stable')
        self.assertEqual(self.ledger.audit(t.speech)['understanding'],'not_inferred_from_delivery')
    def test_unextracted_plan_never_claims_full_coverage(self):
        self.assertFalse(self.ledger.audit([])['coverage_verified'])
        self.assertIn('follow_up',self.ledger.audit([])['unverified_plan_fields'])
    def test_same_record_does_not_create_a_spurious_revision(self):
        self.ledger.update(self.note)
        self.assertEqual(len(self.ledger.versions),1)
    def test_critical_qualifier_cannot_disappear(self):
        self.note['P']['education']='흉통 시 즉시 응급실 방문.'
        self.ledger.update(self.note)
        row=deepcopy(self.row);row['source_quote']=self.note['P']['education']
        with self.assertRaises(ValueError):self.ledger.register({'obligations':[row]})
    def test_whole_group_requires_every_acknowledged_message(self):
        row=deepcopy(self.row);row['messages'].append('다른 증상도 알려 주세요.')
        self.ledger.register({'obligations':[row]})
        self.assertEqual(len(self.ledger.audit([{'index':0,'record_count':1,'content':row['messages'][0]}])['unresolved_ids']),1)
    def test_timing_cannot_be_claimed_when_missing_from_speech(self):
        row=deepcopy(self.row);row['timing']='3일 후'
        with self.assertRaises(ValueError):self.ledger.register({'obligations':[row]})
    def test_final_adapter_does_not_run_legacy_completion_rewrite(self):
        from nova_agent.e2_safety_obligations import Client
        class Capture:
            def diagnose(self,**kwargs):return kwargs
        timeline=SafetyTimeline();timeline.obligations=self.ledger
        result=Client(Capture(),timeline).diagnose(note=self.note,diagnosis='가설',request_id='final-stable')
        self.assertEqual(result['request_id'],'final-stable')
        self.assertIn('수행 여부 미확인',result['note']['P']['education'])
        self.assertEqual(result['note']['S'],self.note['S'])
    def test_closing_reserves_turns_and_never_splits_a_group(self):
        import sys,json
        from pathlib import Path
        from unittest.mock import patch
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
        from examples import hybrid_comm as C,hybrid_agent as H
        from nova_agent import e2_safety_obligations as S2
        from datetime import datetime,timezone,timedelta
        class Fake:
            def session(self):return {'turns_remaining':4,'deadline_at':(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()}
            def chat(inner,*a,**kw):
                row=deepcopy(self.row);row['messages'].append('다른 증상도 알려 주세요.')
                return {'choices':[{'message':{'content':json.dumps({'obligations':[row]},ensure_ascii=False)}}]}
        t=SafetyTimeline()
        with patch.object(C,'_closing_sentences',return_value=['기본 설명이에요.','다른 설명이에요.']),patch.object(H,'write_record'):
            original=S2.install(t)
            try:
                # The two-message obligation cannot fit the one available SAY.
                self.assertEqual(C._closing_sentences(Fake(),None,self.note,'가설','',True),[])
                self.assertTrue(t.obligations.audit([])['unresolved_ids'])
            finally:S2.restore(original)
