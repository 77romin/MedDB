import unittest
from unittest.mock import patch
from meddb import MedDB
from examples import reader_b1_observed as R,agent_b1,agent_b1_observed,hybrid_agent as H

class ReaderB2Tests(unittest.TestCase):
    def setUp(self):
        self.db=MedDB.open();R.install(self.db)
        self.kb=H.Tracker(self.db,'weight_loss',40,'F','40세 여성입니다.',{},'clinical','reviewed')
        self.q=self.db.findings['hand_tremor']['ask']
    def observe(self,a,q=None):R.observe(self.kb,self.db,q or self.q,a,1)
    def test_bare_yes(self):
        self.observe('네, 있어요.');self.assertIn('hand_tremor',self.kb.present)
    def test_bare_no(self):
        self.observe('아니요, 없어요.');self.assertIn('hand_tremor',self.kb.absent)
    def test_partial_prefix(self):
        self.observe('아니요, 자주는 아니에요.')
        self.assertNotIn('hand_tremor',self.kb.absent);self.assertNotIn('hand_tremor',self.kb.present)
        self.assertEqual(self.kb.b1_observations[-1]['answer'],'아니요, 자주는 아니에요.')
    def test_other_symptom_denial(self):
        self.observe('설사는 없어요.');self.assertNotIn('hand_tremor',self.kb.absent)
    def test_family(self):
        self.observe('아버지가 손을 떠세요.');self.assertNotIn('hand_tremor',self.kb.present)
    def test_past(self):
        self.observe('예전에 손이 떨렸지만 지금은 괜찮아요.');self.assertNotIn('hand_tremor',self.kb.present)
    def test_uncertain(self):
        self.observe('잘 모르겠어요.');self.assertNotIn('hand_tremor',self.kb.absent)
    def test_two_concept_yes(self):
        original=self.db.match_findings
        def match(text):
            return {'present':['hand_tremor','diarrhea'],'absent':[],'unknown':[]} if text=='two?' else original(text)
        with patch.object(self.db,'match_findings',match):self.observe('네.',q='two?')
        self.assertNotIn('hand_tremor',self.kb.present);self.assertNotIn('diarrhea',self.kb.present)
    def test_conflicting_answer(self):
        self.kb.mark('hand_tremor','+',0,'prior');self.observe('아니요, 없어요.')
        self.assertIn('hand_tremor',self.kb.conflicts);self.assertIn('hand_tremor',self.kb.unknown)
    def test_dispatch_and_default(self):
        with patch.object(agent_b1,'consult',return_value='ok') as consult:
            self.assertEqual(agent_b1_observed.consult(object(),self.db),'ok')
            self.assertIs(consult.call_args.kwargs['reader'],R)
        self.assertIs(agent_b1._run.__defaults__[0],agent_b1.G)
    def test_actual_run_uses_one_observation_boundary(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from nova_sdk import empty_record
        reader=SimpleNamespace(install=Mock(),observe=Mock())
        kb=SimpleNamespace(note_seen=Mock())
        v=SimpleNamespace(opening='40세 여성입니다.',age=40,sex='F',vitals={},session={},
                          stopped=False,turn=0,asked=[],qa=[],exams=[],concern='',
                          left=lambda:1000,room=lambda *a:False,
                          closing=lambda *a:[],submit=Mock())
        def say(text,tag):
            v.turn+=1;v.asked.append(text);v.qa.append({'q':text,'a':'네.','tag':tag})
            return '네.'
        v.say=say
        with patch.object(agent_b1,'pick_complaint',return_value='weight_loss'), \
             patch.object(agent_b1,'_step',side_effect=[('SAY',self.q),('DONE','')]), \
             patch.object(H,'Tracker',return_value=kb), \
             patch.object(H,'write_record',return_value=(empty_record(),'진단 미정')):
            agent_b1._run(v,object(),self.db,reader)
        reader.observe.assert_called_once()
        self.assertEqual(reader.observe.call_args.args[3],'네.')
        kb.note_seen.assert_called_once_with(v.opening,0)
        v.submit.assert_called_once()
