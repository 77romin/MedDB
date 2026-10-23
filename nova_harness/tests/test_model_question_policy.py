import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
from meddb import MedDB
from examples import hybrid_agent as H,hybrid_care,hybrid_comm
from nova_agent import model_question_policy as P,response_state,coverage_order,e2_observation_state
from nova_sdk import NovaError,empty_record

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.db=MedDB.open();self.events=[]
        self.kb=SimpleNamespace(db=self.db,observations=SimpleNamespace(snapshot=lambda:{'facts':[{'quote':'실제 원문'}]}))
        self.care=SimpleNamespace(extra={},response_slots={},allow_action=lambda k,kind,text,target:target!='allergy')
        self.menu=[{'type':'SAY','text':'언제부터 불편하셨나요?','target':'onset','priority':1},
                   {'type':'SAY','text':'증상은 어떻게 변했나요?','target':'course','priority':1}]
    def choose(self,outputs,required=None):
        with patch.object(H,'chat',side_effect=outputs) as chat:
            result=P.select(None,self.kb,self.care,self.menu if required is None else required,[],
                            '현재 문맥',['의사: 이전 질문?','환자: 실제 원문'],20,self.events)
        return result,chat
    def test_model_can_choose_nonfirst_with_ledger_and_full_context(self):
        (step,chosen,req),chat=self.choose(['{"menu_id":2,"reason":"경과 확인"}'])
        self.assertEqual(chosen['target'],'course')
        payload=json.loads(chat.call_args.args[2]);self.assertEqual(payload['full_transcript'][-1],'환자: 실제 원문')
        self.assertEqual(payload['observations']['facts'][0]['quote'],'실제 원문')
    def test_protected_risk_never_calls_model(self):
        risk=dict(self.menu[0],priority=0)
        (_,chosen,_),chat=self.choose([],required=[risk,*self.menu]);self.assertEqual(chosen,risk);chat.assert_not_called()
    def test_free_detail_keeps_unknown_target(self):
        (step,chosen,_),_=self.choose([json.dumps({'action':'SAY','content':'하루에 몇 번 그러세요?'})])
        self.assertIsNone(chosen['target']);self.assertIn('몇 번',step['content'])
    def test_completed_target_rejected_then_menu(self):
        self.care.response_slots['onset']={'status':'received'}
        (_,chosen,_),chat=self.choose(['{"action":"SAY","content":"언제 시작됐나요?","target":"onset"}','{"menu_id":2}'])
        self.assertEqual(chosen['target'],'course');self.assertEqual(chat.call_count,2)
    def test_unknown_target_never_written_to_kb(self):
        (_,chosen,_),_=self.choose(['{"action":"SAY","content":"왜 그러셨나요?","target":"invented"}','{"menu_id":2}'])
        self.assertEqual(chosen['target'],'course');self.assertEqual(self.events[0]['reason'],'unknown_target')
    def test_invalid_done_cannot_add_early_exit(self):
        (step,chosen,_),_=self.choose(['{"action":"DONE"}','{"action":"DONE"}'])
        self.assertEqual(step['action'],'SAY');self.assertEqual(chosen,self.menu[0]);self.assertEqual(self.events[-1]['selection'],'fallback')
    def test_transport_error_falls_back(self):
        (_,chosen,_),_=self.choose([NovaError('PROVIDER_ERROR')]);self.assertEqual(chosen,self.menu[0])
    def test_untrusted_malformed_output_falls_back(self):
        (_,chosen,_),_=self.choose(['[]','{"menu_id":true}']);self.assertEqual(chosen,self.menu[0])
    def test_question_format_and_compound(self):
        for text in ('모두 말씀해 주세요?','열 또는 기침이 있나요?','왜요?\n어디요?','가'*31+'?','진단은 확정입니다.'):
            self.assertFalse(P.fits_question(text))
    def test_real_combination_hooks_selected_consult_and_restores(self):
        events=[];ledgers=[];r=response_state.install(events);o=coverage_order.install(events)
        original=hybrid_care.base_consult
        try:
            u=e2_observation_state.install(events,ledgers);unified=hybrid_care.base_consult
            try:
                q=P.install(events)
                try:
                    g=hybrid_care.base_consult.__globals__
                    self.assertIn('_model_question_choose',g)
                    self.assertIn('kb.observe_response',e2_observation_state.patched_source(Path(hybrid_comm.__file__).read_text()))
                    # Exercise actual selected consult -> selector -> SAY -> ledger -> writer -> diagnose.
                    class Client:
                        turn=0
                        def session(self):return {'initial':{'opening':'성인입니다.','vital_signs':{}},'turns_remaining':50}
                        def say(self,text,**kw):self.turn+=1;return {'turn':self.turn,'content':'특이사항 없어요.'}
                        def diagnose(self,**kw):self.final=kw;return kw
                        def chat(self,*a,**kw):return {'choices':[{'message':{'content':'{}'}}]}
                    c=Client();calls=[]
                    def selector(*args):
                        calls.append(1)
                        return P._chosen(self.menu[0]) if len(calls)==1 else ({'action':'DONE'},None,[])
                    with patch.dict(g,{'_model_question_choose':selector,'pick_complaint':lambda *a:None,
                                       '_closing_sentences':lambda *a,**kw:[]}):
                        with patch.object(H,'write_record',lambda *a,**kw:(empty_record(),'진단 미정')):
                            hybrid_care.consult(c,self.db,knowledge_mode='clinical',reference_profile='reviewed')
                    self.assertGreaterEqual(len(calls),2);self.assertTrue(hasattr(c,'final'))
                    self.assertTrue(any(e.target=='onset' for e in ledgers[0].state.evidence))
                finally:P.restore(q)
                self.assertIs(hybrid_care.base_consult,unified)
            finally:e2_observation_state.restore(u)
        finally:coverage_order.restore(o);response_state.restore(r)
        self.assertIs(hybrid_care.base_consult,original)

if __name__=='__main__':unittest.main()
