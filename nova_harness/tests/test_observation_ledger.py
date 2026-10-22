import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import MedDB
from nova_agent.observation_ledger import ObservationLedger

class LedgerTests(unittest.TestCase):
    def setUp(self):self.ledger=ObservationLedger(MedDB.open())
    def fact(self,e,fid='diarrhea',assertion='present',subject='patient',time='current',scope='full',**kw):
        return dict(dict(concept_id=fid,evidence_id=e.id,quote=e.response,assertion=assertion,subject=subject,temporality=time,scope=scope),**kw)
    def evidence(self,text,target='diarrhea',turn=1):
        e=self.ledger.state.add_response('SAY','질문?',{'content':text,'turn':turn},target)
        self.ledger.targets[target]=e.id;return e
    def accept(self,e,rows):return self.ledger.accept({'facts':rows},e,['diarrhea','palpitations','abdominal_pain'])
    def test_family_past_conditional_do_not_fill_patient_current(self):
        for subject,time in [('family','current'),('patient','past'),('patient','conditional')]:
            e=self.evidence('두근거림이 있어요.','palpitations')
            self.accept(e,[self.fact(e,'palpitations',subject=subject,time=time)])
        self.assertEqual(self.ledger.view()[0]['palpitations'],'?')
        self.assertEqual(len(self.ledger.state.facts),3)
    def test_current_negative_and_past_positive_are_not_conflicting(self):
        e=self.evidence('예전에는 설사가 있었지만 지금은 없어요.')
        self.accept(e,[self.fact(e,time='past'),self.fact(e,assertion='absent')])
        self.assertEqual(self.ledger.view(),({'diarrhea':'-'},set()))
    def test_qualified_absence_is_preserved_but_not_absolute(self):
        e=self.evidence('거의 없어요.')
        self.accept(e,[self.fact(e,assertion='absent',qualifiers=[{'name':'frequency','quote':'거의'}])])
        self.assertEqual(self.ledger.view()[0]['diarrhea'],'?')
        self.assertEqual(self.ledger.state.facts[0]['qualifiers'][0]['quote'],'거의')
    def test_unanswered_target_is_not_negative(self):
        e=self.evidence('설사는 없어요.','abdominal_pain')
        self.accept(e,[self.fact(e,assertion='absent')])
        self.assertEqual(self.ledger.view()[0],{'diarrhea':'-','abdominal_pain':'?'})
    def test_mixed_invalid_row_does_not_discard_valid(self):
        e=self.evidence('설사는 없어요.')
        good=self.fact(e,assertion='absent');bad=dict(good,quote='없는 원문')
        valid,rejected=self.accept(e,[good,bad])
        self.assertEqual(len(valid),1);self.assertTrue(rejected)
    def test_foreign_evidence_and_new_qualifier_are_rejected(self):
        e=self.evidence('설사가 있어요.')
        for row in [self.fact(e,evidence_id='foreign'),self.fact(e,qualifiers=[{'name':'duration','quote':'3년'}])]:
            self.assertEqual(self.accept(e,[row])[0],[])
    def test_conflict_retains_both_sources(self):
        for turn,text,assertion in [(1,'설사가 있어요.','present'),(2,'설사가 없어요.','absent')]:
            e=self.evidence(text,turn=turn);self.accept(e,[self.fact(e,assertion=assertion)])
        self.assertEqual(self.ledger.view(),({'diarrhea':'?'},{'diarrhea'}))
        self.assertEqual(len(self.ledger.state.evidence),2)
    def test_explicit_correction_can_replace_same_scope_only(self):
        e=self.evidence('설사가 없어요.');self.accept(e,[self.fact(e,assertion='absent')]);old=self.ledger.state.facts[0]['id']
        e=self.evidence('정정할게요. 설사가 있어요.',turn=2)
        self.accept(e,[self.fact(e,replaces=[old],correction_quote='정정할게요.')])
        self.assertEqual(self.ledger.view(),({'diarrhea':'+'},set()))
        self.assertEqual(len(self.ledger.state.facts),2)
    def test_correction_cannot_replace_other_concept_or_subject(self):
        e=self.evidence('설사가 없어요.');self.accept(e,[self.fact(e,assertion='absent')]);old=self.ledger.state.facts[0]['id']
        e=self.evidence('어머니는 설사가 있어요.',turn=2)
        valid,_=self.accept(e,[self.fact(e,subject='family',replaces=[old],correction_quote='설사가 있어요.')])
        self.assertFalse(valid);self.assertEqual(self.ledger.view()[0]['diarrhea'],'-')
    def test_failed_extractor_keeps_raw_and_unknown(self):
        class Client:
            def chat(self,*a,**kw):raise RuntimeError('synthetic')
        self.ledger.observe(Client(),'설사가 있나요?','잘 모르겠어요.','diarrhea',1)
        self.assertEqual(self.ledger.view()[0]['diarrhea'],'?')
        self.assertEqual(self.ledger.state.evidence[0].response,'잘 모르겠어요.')
        self.assertEqual(len(self.ledger.failures),1)
    def test_qualified_positive_is_not_collapsed_to_binary(self):
        e=self.evidence('거의 없어요.')
        self.accept(e,[self.fact(e,qualifiers=[{'name':'frequency','quote':'거의'}])])
        self.assertEqual(self.ledger.view()[0]['diarrhea'],'?')
        self.assertEqual(self.ledger.state.facts[0]['assertion'],'present')

    def test_bad_quote_type_does_not_crash_valid_row(self):
        e=self.evidence('설사가 있어요.')
        valid,rejected=self.accept(e,[self.fact(e,quote=123),self.fact(e)])
        self.assertEqual(len(valid),1);self.assertTrue(rejected)

    def test_family_answer_completion_is_distinct_from_current_patient(self):
        e=self.evidence('어머니는 두근거림이 있어요.','palpitations')
        payload={'facts':[self.fact(e,'palpitations',subject='family')],
                 'answer_contract':{'subject':'family','temporality':'current','status':'complete','quote':e.response}}
        self.ledger.accept(payload,e,['palpitations'])
        self.assertEqual(self.ledger.answer_status['palpitations']['status'],'complete')
        self.assertEqual(self.ledger.view()[0]['palpitations'],'?')

    def test_past_answer_completion_does_not_assert_current_symptom(self):
        e=self.evidence('예전에는 설사가 있었어요.')
        self.ledger.accept({'facts':[self.fact(e,time='past')],
                            'answer_contract':{'subject':'patient','temporality':'past','status':'complete','quote':e.response}},e,['diarrhea'])
        self.assertEqual(self.ledger.answer_status['diarrhea']['status'],'complete')
        self.assertEqual(self.ledger.view()[0]['diarrhea'],'?')

    def test_other_concept_cannot_complete_target_contract(self):
        e=self.evidence('설사는 없어요.','abdominal_pain')
        self.ledger.accept({'facts':[self.fact(e,assertion='absent')],
                            'answer_contract':{'subject':'patient','temporality':'current','status':'complete','quote':e.response}},e,['diarrhea','abdominal_pain'])
        self.assertNotEqual(self.ledger.answer_status['abdominal_pain']['status'],'complete')

    def test_ontology_history_scope_is_retained_without_current_symptom_leak(self):
        for fid,subject,text in [('family_late_puberty','family','아버지가 늦었어요.'),
                                 ('birth_abnormal','patient','미숙아였어요.')]:
            e=self.evidence(text,target=fid)
            self.ledger.accept({'facts':[self.fact(e,fid,subject=subject,time='past')]},e,[fid])
            self.assertEqual(self.ledger.view()[0][fid],'+')
            self.assertEqual(self.ledger.current_view()[0][fid],'?')
        e=self.evidence('어머니는 두근거림이 있어요.',target='palpitations')
        self.accept(e,[self.fact(e,'palpitations',subject='family')])
        self.assertEqual(self.ledger.view()[0]['palpitations'],'?')

    def test_once_per_observation_batch(self):
        class Client:
            calls=0
            def chat(self,*a,**kw):self.calls+=1;return {'choices':[{'message':{'content':'{"facts":[]}'}}]}
        client=Client();self.ledger.observe(client,'질문?','설사와 두근거림이 있어요.',None,1)
        self.assertEqual(client.calls,1)

if __name__=='__main__':unittest.main()
