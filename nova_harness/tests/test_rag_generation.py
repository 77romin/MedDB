import unittest
from types import SimpleNamespace
from nova_agent.rag_generation import GenerationClient,SYSTEM


class GenerationTests(unittest.TestCase):
    def test_record_only_immutable_input_and_no_extra_call(self):
        calls=[];events=[]
        client=SimpleNamespace(chat=lambda messages,**kwargs:calls.append((messages,kwargs)) or 'result',session=lambda:{})
        proxy=GenerationClient(client,events)
        messages=[{'role':'system','content':'진료 기록만 근거로 초진 기록을 완성합니다. contextual schema'},
                  {'role':'user','content':'actual observations'}]
        self.assertEqual(proxy.chat(messages,max_tokens=4096),'result')
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0][0][0]['content'].endswith(SYSTEM))
        self.assertFalse(messages[0]['content'].endswith(SYSTEM))
        self.assertEqual(calls[0][0][1],messages[1])
        self.assertEqual(len(events),1)
        self.assertEqual(proxy.session(),{})

    def test_query_selector_and_closing_requests_unchanged(self):
        from nova_agent.rag_query import SYSTEM as QUERY
        from nova_agent.rag_selector import SYSTEM as SELECT
        calls=[];events=[]
        proxy=GenerationClient(SimpleNamespace(chat=lambda m,**kw:calls.append(m)),events)
        for text in (QUERY,SELECT,'진료 마지막에 환자가 한 질문에 답합니다.'):
            messages=[{'role':'system','content':text}]
            proxy.chat(messages,max_tokens=1024)
            self.assertIs(calls[-1],messages)
        self.assertEqual(events,[])
