import unittest
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import MedDB,coverage
from nova_agent import coverage_order,response_state

class OrderTests(unittest.TestCase):
    def setUp(self):
        self.original=coverage.CareCoverage;self.events=[]
        self.r=response_state.install(self.events)
        self.o=coverage_order.install(self.events)
        self.c=coverage.CareCoverage(MedDB.open(),'insomnia',40,'F')
        self.k=SimpleNamespace(conflicts=set(),asked=set(),present=set(),absent=set(),exams_done=set())
    def tearDown(self):
        coverage_order.restore(self.o);response_state.restore(self.r)
        self.assertIs(coverage.CareCoverage,self.original)
    def action(self,target,priority=2,kind='SAY'):
        return {'target':target,'type':kind,'text':'질문?', 'priority':priority}
    def test_safety_and_urgent_preserved_without_new_candidates(self):
        acts=[self.action('impact'),self.action('allergy',3),self.action('onset',1),self.action('danger',0)]
        before=deepcopy(acts);out,_=coverage_order.order(self.c,self.k,acts)
        self.assertEqual([a['target'] for a in out],['danger','onset','allergy','impact'])
        self.assertEqual(acts,before)
        self.assertEqual({id(a) for a in acts},{id(a) for a in out})
    def test_observed_domain_changes_order_not_diagnosis(self):
        self.c.observe('impact','불편한 점은요?','일하기 힘들어요',2)
        acts=[self.action('sleep_hours'),self.action('family',3)]
        before=deepcopy(vars(self.k));out,counts=coverage_order.order(self.c,self.k,acts)
        self.assertEqual(out[0]['target'],'family')
        self.assertEqual(counts['hpi'],1)
        self.assertEqual(vars(self.k),before)
    def test_ambiguous_or_refused_does_not_fill_domain(self):
        for answer in ('잘 모르겠어요','말하기 싫어요'):
            self.c.observe('impact','불편한 점은요?',answer,2)
            acts=[self.action('sleep_hours'),self.action('family',3)]
            out,counts=coverage_order.order(self.c,self.k,acts)
            self.assertEqual(out,acts);self.assertEqual(counts,{})
    def test_exam_not_promoted_before_history_or_over_urgent(self):
        acts=[self.action('impact'),self.action('ex_mental',4,'EXAM')]
        out,_=coverage_order.order(self.c,self.k,acts);self.assertEqual(out,acts)
        for i in range(8):self.c.response_slots['item'+str(i)]={'status':'received','turn':i}
        out,_=coverage_order.order(self.c,self.k,acts);self.assertEqual(out[0]['type'],'EXAM')
        urgent=self.action('danger',0)
        out,_=coverage_order.order(self.c,self.k,acts+[urgent]);self.assertIs(out[0],urgent)
    def test_same_topic_stable_order_and_already_answered_filter(self):
        self.c.observe('sleep_hours','하루에 실제로 몇 시간 주무세요?','네 시간',2)
        acts=self.c.needed(self.k)
        self.assertFalse(any(a['target']=='sleep_hours' for a in acts))
        self.assertTrue(any(e['event']=='coverage_order' for e in self.events))
        self.assertFalse(self.c.allow_action(self.k,'SAY','하루에 실제로 몇 시간 주무세요?',None))
    def test_real_required_set_is_permutation(self):
        base=self.o.needed(self.c,self.k)
        result=self.c.needed(self.k)
        sig=lambda xs:sorted((a['type'],a['target'],a['text']) for a in xs)
        self.assertEqual(sig(base),sig(result))
    def test_unknown_exam_target_and_absent_risk_not_invented(self):
        acts=[self.action('family',3)]
        out,_=coverage_order.order(self.c,self.k,acts)
        self.assertEqual(out,acts)
        self.assertNotIn('pregnancy',[a['target'] for a in out])

if __name__=='__main__':unittest.main()
