from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import MedDB,coverage
from examples import hybrid_care,hybrid_agent as H
from nova_sdk import empty_record,NovaError
from nova_agent import response_state,coverage_order,e2_observation_state
from nova_agent.observation_ledger import SYSTEM

class UnifiedSessionTests(unittest.TestCase):
    def run_session(self,answer,rows,target='abdominal_pain',fail=False,extractor_error=False):
        db=MedDB.open();events=[];ledgers=[];captured={};question=db.findings[target]['ask']
        class Client:
            turn=0
            extraction_calls=0
            record_inputs=[]
            def session(self):return {'initial':{'opening':'30세 여성입니다.','vital_signs':{}},'turns_remaining':50}
            def say(self,text,**kwargs):
                if text==question and fail:raise NovaError('SESSION_CLOSED')
                self.turn+=1;return {'content':answer if text==question else '아니요.',
                                    'turn':self.turn,'turns_remaining':50-self.turn}
            def chat(self,messages,**kwargs):
                if messages[0]['content']==SYSTEM:
                    self.extraction_calls+=1
                    if extractor_error:raise RuntimeError('synthetic extractor failure')
                    src=json.loads(messages[1]['content']);facts=[]
                    for row in rows:
                        fact={'evidence_id':src['evidence_id'],'quote':src['response'],'assertion':'present',
                              'subject':'patient','temporality':'current','scope':'full'}
                        fact.update(deepcopy(row));facts.append(fact)
                    return {'choices':[{'message':{'content':json.dumps({'facts':facts})}}]}
                self.record_inputs.append(deepcopy(messages))
                return {'choices':[{'message':{'content':'{}'}}]}
            def diagnose(self,**kwargs):captured['submitted']=deepcopy(kwargs);return kwargs
        client=Client()
        def writer(client,db,kb,opening,vitals,transcript,contextual_plan=False):
            captured['view']={'present':list(kb.present),'absent':list(kb.absent),'unknown':list(kb.unknown)}
            captured['transcript']=list(transcript)
            client.chat([{'role':'system','content':H.RECORD_SYSTEM},{'role':'user','content':'진료 기록'}],max_tokens=4096)
            note=empty_record();note['S']['hpi']='\n'.join(transcript)
            return note,'진단 미정'
        original_consult=hybrid_care.base_consult;original_tracker=H.Tracker;original_coverage=coverage.CareCoverage
        r=response_state.install(events);o=coverage_order.install(events)
        try:
            with patch.object(H,'write_record',writer):
                u=e2_observation_state.install(events,ledgers)
                try:
                    g=hybrid_care.base_consult.__globals__
                    def needed(self,kb):
                        return [] if target in self.records else [{'type':'SAY','target':target,'text':question,'priority':2}]
                    def next_step(*args):
                        captured['next_step_user']=args[2]
                        return '{"action":"DONE"}'
                    with patch.dict(g,{'pick_complaint':lambda *a:'weight_loss',
                                       'read_answer':lambda *a:(_ for _ in ()).throw(AssertionError('old interpreter called')),
                                       '_closing_sentences':lambda *a,**kw:[]}):
                        with patch.object(coverage.CareCoverage,'needed',needed),patch.object(H,'chat',next_step):
                            hybrid_care.consult(client,db,knowledge_mode='clinical',reference_profile='reviewed')
                finally:e2_observation_state.restore(u)
        finally:coverage_order.restore(o);response_state.restore(r)
        self.assertIs(H.Tracker,original_tracker);self.assertIs(hybrid_care.base_consult,original_consult)
        self.assertIs(coverage.CareCoverage,original_coverage)
        captured['ledger']=ledgers[0].snapshot();captured['client']=client
        return captured
    def test_other_symptom_denial_never_becomes_target_denial(self):
        data=self.run_session('설사는 없어요.',[{'concept_id':'diarrhea','assertion':'absent'}])
        self.assertNotIn('abdominal_pain',data['view']['absent'])
        self.assertIn('abdominal_pain',data['view']['unknown'])
        self.assertIn('diarrhea',data['view']['absent'])
        self.assertIn('설사는 없어요.',data['submitted']['note']['S']['hpi'])
        self.assertIn('"abdominal_pain": "?"',data['client'].record_inputs[0][-1]['content'])
        self.assertEqual(data['client'].extraction_calls,1)
    def test_past_present_and_family_stay_separate_through_record_boundary(self):
        data=self.run_session('예전에는 설사가 있었지만 지금은 없어요.',
                [{'concept_id':'diarrhea','temporality':'past'},
                 {'concept_id':'diarrhea','assertion':'absent'}],target='diarrhea')
        self.assertIn('diarrhea',data['view']['absent']);self.assertNotIn('diarrhea',data['view']['present'])
        self.assertEqual(len(data['ledger']['facts']),2)
        data=self.run_session('어머니는 두근거림이 있어요.',
                             [{'concept_id':'palpitations','subject':'family'}],target='palpitations')
        self.assertNotIn('palpitations',data['view']['present'])
        self.assertEqual(data['ledger']['facts'][0]['subject'],'family')
    def test_failed_say_never_creates_patient_evidence(self):
        data=self.run_session('설사가 있어요.',[{'concept_id':'diarrhea'}],target='diarrhea',fail=True)
        self.assertEqual(data['client'].extraction_calls,0)
        self.assertFalse(data['ledger']['facts'])
        self.assertNotIn('설사가 있어요.',data['submitted']['note']['S']['hpi'])
    def test_extractor_failure_keeps_raw_and_no_binary_guess(self):
        data=self.run_session('네, 설사가 있어요.',[],target='diarrhea',extractor_error=True)
        self.assertNotIn('diarrhea',data['view']['present']);self.assertIn('diarrhea',data['view']['unknown'])
        self.assertIn('네, 설사가 있어요.',data['submitted']['note']['S']['hpi'])
    def test_completed_family_history_does_not_trigger_current_symptom_requestion(self):
        from types import SimpleNamespace
        db=MedDB.open();events=[];r=response_state.install(events);o=coverage_order.install(events)
        u=e2_observation_state.install(events)
        try:
            care=coverage.CareCoverage(db,'short_stature',8,'M')
            kb=H.Tracker(db,'short_stature',8,'M','',{},'clinical','reviewed')
            t='family_late_puberty';question=db.findings[t]['ask'];answer='아버지가 늦었어요.'
            e=kb.observations.state.add_response('SAY',question,{'content':answer,'turn':2},t)
            kb.observations.targets[t]=e.id
            kb.observations.accept({'facts':[{'concept_id':t,'evidence_id':e.id,'quote':answer,
                                      'assertion':'present','subject':'family','temporality':'past','scope':'full'}],
                                   'answer_contract':{'subject':'family','temporality':'past','status':'complete','quote':answer}},e,[t])
            care.observe(t,question,answer,2);care.sync_observation(kb,t)
            care.attempts[t]=1;kb.asked.add(t)
            self.assertEqual(care.response_slots[t]['status'],'received')
            self.assertEqual(kb.observations.current_view()[0][t],'?')
            self.assertEqual(kb.observations.view()[0][t],'+')
            self.assertFalse(any(a.get('target')==t and a.get('_response_clarification') for a in care.needed(kb)))
        finally:e2_observation_state.restore(u);coverage_order.restore(o);response_state.restore(r)

    def test_source_contract_change_fails_closed(self):
        with self.assertRaises(ValueError):e2_observation_state.patched_source('different source')

if __name__=='__main__':unittest.main()
