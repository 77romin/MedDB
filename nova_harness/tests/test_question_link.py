import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import MedDB,coverage
from nova_agent.question_link import QuestionIndex,propose
from nova_agent import e2_question_link,response_state,coverage_order

class LinkTests(unittest.TestCase):
    def setUp(self):
        self.db=MedDB.open();self.index=QuestionIndex(self.db,{},30,'F')
    def test_duration_and_present_scope_retained(self):
        for q in ('기침이 2주 넘게 계속되시나요?','기침이 2주 넘게 계속되고 있나요?'):
            self.assertEqual(self.index.resolve(q),('chronic_cough','bounded_variant'))
    def test_actual_historical_question_is_not_current_duration(self):
        self.assertEqual(self.index.resolve('기침이 2주 넘게 계속된 적 있나요?'),(None,'historical_scope'))
    def test_number_negation_and_subject_changes_abstain(self):
        for q in ('기침이 3주 넘게 계속되시나요?','기침이 계속되시나요?',
                  '기침이 2주 넘게 계속되지 않나요?','아버지 기침이 2주 넘게 계속되시나요?'):
            self.assertIsNone(self.index.resolve(q)[0])
    def test_compound_and_statement_abstain(self):
        for q in ('기침이 2주 넘게 계속되시나요? 열도 있나요?',
                  '기침이 2주 넘게 계속되시나요, 열은요?',
                  '기침이 2주 넘게 계속되시나요.','기침이 2주 넘게 계속되시나요? 아니요.'):
            self.assertIsNone(self.index.resolve(q)[0])
    def test_identical_question_for_two_targets_abstains(self):
        index=QuestionIndex(self.db,{'fake':('기침이 2주 넘게 계속되시나요?', 'hpi')},30,'F')
        self.assertEqual(index.resolve('기침이 2주 넘게 계속되시나요?'),(None,'ambiguous'))
    def test_medication_identity_is_not_usage_or_dose(self):
        names=['약 이름을 알려주시겠어요?','그 약을 몇 알 드시나요?','무슨 약을 얼마나 드시나요?']
        for q in names:
            self.assertNotEqual(self.index.resolve(q)[0],'meds')
    def test_demographic_filter_preserved(self):
        db=SimpleNamespace(slots={'adult':{'ask':'불편한 점이 있나요?'}},findings={},_fits=lambda r,a,s:False)
        self.assertIsNone(QuestionIndex(db,{},5,'M').resolve('불편한 점이 있으세요?')[0])
    def test_guard_restores_exact_original_consult(self):
        from examples import hybrid_care
        original=hybrid_care.base_consult;original_class=coverage.CareCoverage
        events=[];r=response_state.install(events);o=coverage_order.install(events);l=e2_question_link.install(events)
        try:
            care=coverage.CareCoverage(self.db,'weight_loss',30,'F')
            q='기침이 2주 넘게 계속되고 있나요?'
            self.assertEqual(propose(care,q,events),'chronic_cough')
            self.assertEqual(care.question_link_observations,[])
            self.assertEqual(care.records,{})
            care.observe('chronic_cough',q,'잘 모르겠어요',5)
            self.assertEqual(care.response_slots['chronic_cough']['status'],'ambiguous')
            self.assertEqual(care.question_link_observations[0]['answer'],'잘 모르겠어요')
            self.assertEqual(sum(e['event']=='question_link_observed' for e in events),1)
        finally:e2_question_link.restore(l);coverage_order.restore(o);response_state.restore(r)
        self.assertIs(hybrid_care.base_consult,original);self.assertIs(coverage.CareCoverage,original_class)
    def test_new_duplicate_checks_recovered_target(self):
        events=[];r=response_state.install(events);o=coverage_order.install(events);l=e2_question_link.install(events)
        try:
            care=coverage.CareCoverage(self.db,'weight_loss',30,'F')
            care.observe('chronic_cough','기침이 2주 넘게 계속되나요?','없어요',3)
            q='기침이 2주 넘게 계속되고 있나요?';target=propose(care,q,events)
            kb=SimpleNamespace(exams_done=set())
            self.assertFalse(care.allow_action(kb,'SAY',q,target))
            self.assertEqual(len(care.response_history),1)
            self.assertEqual(care.question_link_observations,[])
            self.assertEqual(care._pending_question_links,{})
        finally:e2_question_link.restore(l);coverage_order.restore(o);response_state.restore(r)
    def test_source_drift_fails_closed(self):
        with self.assertRaises(ValueError):e2_question_link.patched_source('changed contract')


class LinkConsultTests(unittest.TestCase):
    def run_consult(self,question,fail=False):
        from unittest.mock import patch
        from examples import hybrid_care,hybrid_agent as H
        from nova_sdk import empty_record,NovaError
        events=[];r=response_state.install(events);o=coverage_order.install(events);l=e2_question_link.install(events)
        captured={};care_class=coverage.CareCoverage
        class Client:
            def __init__(self):self.turn=0
            def session(self):return {'initial':{'opening':'30세 여성입니다.','vital_signs':{}},'turns_remaining':50}
            def say(self,text):
                if text==question and fail:raise NovaError('SESSION_CLOSED')
                self.turn+=1
                return {'content':'아니요.','turn':self.turn,'turns_remaining':50-self.turn}
            def diagnose(self,**kwargs):return kwargs
        def writer(client,db,kb,opening,vitals,transcript,contextual_plan=False):
            captured['absent']=list(kb.absent);captured['asked']=set(kb.asked)
            captured['transcript']=list(transcript)
            return empty_record(),'진단 미정'
        g=hybrid_care.base_consult.__globals__
        steps=iter([__import__('json').dumps({'action':'SAY','content':question}),'{"action":"DONE"}'])
        try:
            with patch.dict(g,{'pick_complaint':lambda *a:'weight_loss',
                                'read_answer':lambda *a:'-',
                                '_closing_sentences':lambda *a,**kw:[]}):
                with patch.object(care_class,'needed',lambda *a:[]),patch.object(H,'chat',lambda *a:next(steps)),patch.object(H,'write_record',writer):
                    hybrid_care.consult(Client(),MedDB.open(),knowledge_mode='clinical',reference_profile='reviewed')
        finally:e2_question_link.restore(l);coverage_order.restore(o);response_state.restore(r)
        return captured,events
    def test_successful_reply_uses_original_answer_interpreter(self):
        q='기침이 2주 넘게 계속되고 있나요?';data,events=self.run_consult(q)
        self.assertIn('chronic_cough',data['asked']);self.assertIn('chronic_cough',data['absent'])
        self.assertIn('의사: '+q,data['transcript'])
        self.assertEqual(sum(e['event']=='question_link_observed' for e in events),1)
    def test_failed_action_has_no_observed_link_or_fact(self):
        data,events=self.run_consult('기침이 2주 넘게 계속되고 있나요?',fail=True)
        self.assertNotIn('chronic_cough',data['asked']);self.assertNotIn('chronic_cough',data['absent'])
        self.assertEqual(sum(e['event']=='question_link_observed' for e in events),0)
    def test_historical_reply_is_not_misread_as_current_negative(self):
        data,events=self.run_consult('기침이 2주 넘게 계속된 적 있나요?')
        self.assertNotIn('chronic_cough',data['asked']);self.assertNotIn('chronic_cough',data['absent'])
        self.assertTrue(any(e.get('reason')=='historical_scope' for e in events))

if __name__=='__main__':unittest.main()
