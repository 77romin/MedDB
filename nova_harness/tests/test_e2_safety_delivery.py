import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from copy import deepcopy
from nova_agent.safety_trace import SafetyTimeline
from nova_agent import e2_safety_delivery as delivery

class ClosingIntegrationTests(unittest.TestCase):
    def run_closing(self,fields,repair=None,coverage=False,coverage_response=None):
        responses=[]
        note={'P':{'education':'경련이 생기면 응급실로 가세요.'}}
        original_note=deepcopy(note)
        def chat(messages,**kw):
            responses.append(kw)
            content=fields if isinstance(fields,str) else json.dumps(fields,ensure_ascii=False)
            if messages[0]['content']==delivery.REPAIR_SYSTEM:content=json.dumps(repair)
            if messages[0]['content']==delivery.COVERAGE_SYSTEM:content=json.dumps(coverage_response)
            return {'choices':[{'message':{'content':content}}]}
        defaults=['진단 설명','검사 설명','재진 설명','일반 안전 설명']
        def original(client,*args):
            client.chat([{'role':'system','content':'외래 진료를 마무리하며'}],max_tokens=1536)
            return defaults
        c=SimpleNamespace(_closing_sentences=original,NO_QUESTION=SimpleNamespace(search=lambda s:False),_nfc=str)
        h=SimpleNamespace(parse_json=json.loads,write_record=lambda *a,**kw:None)
        t=SafetyTimeline();client=SimpleNamespace(chat=chat,session=lambda:{'turns_remaining':12})
        with patch.dict('sys.modules',{'examples':SimpleNamespace(hybrid_comm=c,hybrid_agent=h),
                'examples.consult_skeleton':SimpleNamespace(seconds_left=lambda s:999)}):
            old=delivery.install(t,check_coverage=coverage)
            try:out=c._closing_sentences(client,None,note,'dx','',True)
            finally:delivery.restore(old)
        self.assertEqual(note,original_note)
        self.assertEqual(t.speech,[]) # generated proposals are never "delivered"
        self.assertIs(c._closing_sentences,original)
        return out,responses
    def test_full_warning_sentences_survive_without_an_extra_call(self):
        safety='흉통·숨참·실신·고열 땐 응급실로 가세요. 의식 변화나 심해지는 두근거림도 바로 알려 주세요.'
        out,calls=self.run_closing({'diagnosis':'의심돼요.','plan':'검사할게요.','follow_up':'다시 와 주세요.','safety':safety})
        self.assertIn('흉통·숨참·실신·고열 땐 응급실로 가세요.',out)
        self.assertIn('의식 변화나 심해지는 두근거림도 바로 알려 주세요.',out)
        self.assertNotIn('일반 안전 설명',out);self.assertEqual(len(calls),1)
    def test_partial_json_recovers_complete_fields_and_repairs_only_missing_safety(self):
        payload={'status':'needs_clarification','missing':[{'source_field':'education','source_quote':'경련이 생기면 응급실로 가세요.','messages':['경련이 생기면 응급실로 가세요.']}]}
        out,calls=self.run_closing('{"diagnosis":"의심돼요.","plan":"검사할게요.","follow_up":"다시 와 주세요.","safety":"경',payload)
        self.assertIn('의심돼요.',out);self.assertIn('경련이 생기면 응급실로 가세요.',out)
        self.assertEqual(len(calls),2)
    def test_source_based_missing_warning_is_proposed_once_not_counted_as_delivered(self):
        payload={'status':'needs_clarification','missing':[{'source_field':'education','source_quote':'경련이 생기면 응급실로 가세요.','messages':['경련이 생기면 응급실로 가세요.']}]}
        fields={'diagnosis':'의심돼요.','plan':'검사할게요.','follow_up':'다시 와 주세요.','safety':'불편하면 진료받으세요.'}
        out,calls=self.run_closing(fields,coverage=True,coverage_response=payload)
        self.assertIn('경련이 생기면 응급실로 가세요.',out)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[-1]['max_tokens'],2048)

    def test_unverifiable_repair_is_rejected(self):
        out,calls=self.run_closing({}, {'status':'needs_clarification','missing':[{'source_field':'education','source_quote':'없는 문장','messages':['새로운 처방입니다.']}]})
        self.assertNotIn('새로운 처방입니다.',out)
        self.assertEqual(len(calls),2)

class EducationReconciliationTests(unittest.TestCase):
    def test_only_successful_actual_speech_is_claimed_as_delivered(self):
        t=SafetyTimeline()
        t.speech=[{'record_count':1,'content':'전문의와 상의하세요.','reply':{'content':'네'}},
                  {'record_count':1,'content':'더 궁금하신 점 있으세요?','reply':{'content':'없어요'}}]
        t.failures=[{'action':'SAY','content':'운전하지 마세요.'}]
        note={'S':{'hpi':'actual facts'},'P':{'education':'운전을 피하도록 안내했다. 약을 갑자기 끊지 않도록 설명함.\n환자에게 설명함: 잘못된 수행 주장','treatment':'same plan'}}
        before=deepcopy(note)
        fixed=delivery.reconcile_education(note,t)
        self.assertEqual(note,before)
        self.assertEqual(fixed['P']['treatment'],'same plan')
        self.assertEqual(fixed['S'],note['S'])
        self.assertIn('안내할 계획이다',fixed['P']['education'])
        self.assertIn('설명할 계획임',fixed['P']['education'])
        actual=fixed['P']['education'].split('실제 전달 확인(성공 SAY):',1)[1]
        self.assertIn('전문의와 상의하세요.',actual)
        self.assertNotIn('운전하지 마세요.',actual)
        self.assertNotIn('잘못된 수행 주장',fixed['P']['education'])

class ClosingBudgetTests(unittest.TestCase):
    def test_empty_provider_response_escapes_upstream_repeat_loop(self):
        from nova_sdk import NovaError
        calls=[]
        def failed(messages,**kwargs):
            calls.append(kwargs)
            raise NovaError('PROVIDER_RESPONSE_INVALID',503)
        capture=delivery.CaptureClosing(SimpleNamespace(chat=failed),{'P':{}})
        with self.assertRaises(NovaError) as caught:
            capture.chat([{'role':'system','content':'외래 진료를 마무리하며'}],max_tokens=1536)
        self.assertEqual(caught.exception.code,'LOCAL_CLOSING_RESPONSE_INVALID')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['reasoning_effort'],'low')
