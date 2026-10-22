import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import coverage
from meddb import MedDB
from nova_agent.response_state import install, restore, classify

class ResponseStateTests(unittest.TestCase):
    def setUp(self):
        self.old = coverage.CareCoverage
        self.events=[]
        self.previous=install(self.events)
        self.care=coverage.CareCoverage(MedDB.open(), 'insomnia', 40, 'F')
        self.kb=SimpleNamespace(conflicts=set(), asked=set(),present=set(),absent=set(),exams_done=set())
    def tearDown(self):
        restore(self.previous)
        self.assertIs(coverage.CareCoverage,self.old)
    def test_unknown_not_normal_and_evidence_preserved(self):
        self.care.observe('sleep_hours','몇 시간 주무세요?','잘 모르겠어요',2)
        self.kb.asked.add('sleep_hours')
        before=deepcopy(vars(self.kb))
        options=self.care.needed(self.kb)
        clarification=[a for a in options if a.get('_response_clarification')]
        self.assertEqual(len(clarification),1)
        self.assertEqual(clarification[0]['target'],'sleep_hours')
        self.assertNotEqual(clarification[0]['text'],'몇 시간 주무세요?')
        self.assertLessEqual(len(clarification[0]['text']),30)
        self.assertEqual(vars(self.kb),before)
        self.assertEqual(self.care.records['sleep_hours']['answer'],'잘 모르겠어요')
    def test_partial_quantitative_response_is_bounded(self):
        self.care.observe('sleep_hours','몇 시간 주무세요?','잠을 적게 자요',2)
        self.care.attempts['sleep_hours']=1
        choices=self.care.needed(self.kb)
        q=next(a['text'] for a in choices if a.get('_response_clarification'))
        self.care.observe('sleep_hours',q,'기억 안 나요',3)
        self.assertFalse(any(a.get('_response_clarification') for a in self.care.needed(self.kb)))
        self.assertEqual(len(self.care.response_history),2)
    def test_received_response_blocks_reworded_spacing_not_new_question(self):
        self.care.observe('sleep_hours','몇 시간 주무세요?','네 시간이에요',2)
        self.assertFalse(self.care.allow_action(self.kb,'SAY','몇시간 주무세요!',None))
        self.assertTrue(self.care.allow_action(self.kb,'SAY','깨는 횟수는요?',None))
        self.assertFalse(any(a.get('_response_clarification') for a in self.care.needed(self.kb)))
    def test_refusal_is_not_reasked(self):
        self.care.observe('meds','약 드세요?','말하기 싫어요',2)
        self.assertEqual(self.care.response_slots['meds']['status'],'declined')
        self.assertFalse(any(a.get('_response_clarification') for a in self.care.needed(self.kb)))
    def test_generic_clarification_preserves_topic(self):
        self.care.observe('meds','약 드세요?','잘 모르겠어요',2)
        q=next(a['text'] for a in self.care.needed(self.kb) if a.get('_response_clarification'))
        self.assertIn('약 드세요',q)
    def test_risk_keeps_precedence(self):
        self.care.observe('sleep_hours','몇 시간 주무세요?','잘 모르겠어요',2)
        choices=self.care.needed(self.kb)
        self.assertEqual([a['priority'] for a in choices],sorted(a['priority'] for a in choices))
    def test_classification_is_not_fact_extraction(self):
        self.assertEqual(classify('sleep_hours','몇 시간인지는 몰라요'),'partial')
        self.assertEqual(classify('sleep_hours','전혀 못 자요'),'received')
        self.assertEqual(classify('meds','없어요'),'received')
        self.assertEqual(classify('sleep_hours',''),'ambiguous')

if __name__=='__main__':unittest.main()
