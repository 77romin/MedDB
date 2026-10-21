import importlib.util
import os
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('langgraph'), 'R4 optional LangGraph dependency')
class GraphTests(unittest.TestCase):
    def test_no_candidates_branch_one_generation_call_and_no_external_network(self):
        from nova_agent.rag_graph import install,restore
        from nova_agent import rag_graph
        from nova_agent.rag_generation import SYSTEM
        requests=[]
        note={k:{} for k in ('S','O','A','P')}
        def baseline(client,*args):
            client.chat([{'role':'system','content':'진료 기록만 근거로 초진 기록을 완성합니다.'}],max_tokens=4096)
            return note,'diagnosis'
        h=SimpleNamespace(write_record=baseline)
        client=SimpleNamespace(chat=lambda messages,**kw:requests.append(messages))
        kb=SimpleNamespace(complaint=None)
        with patch.dict('sys.modules',{'examples':SimpleNamespace(hybrid_agent=h)}), \
             patch.dict(os.environ,{'LANGSMITH_TRACING':'true','LANGCHAIN_TRACING_V2':'true'}), \
             patch.object(socket.socket,'connect',side_effect=AssertionError('unexpected external network')):
            old=install(SimpleNamespace(search=lambda *a,**kw:[]))
            try:result=h.write_record(client,SimpleNamespace(diseases={}),kb,'initial',{},[],True)
            finally:restore(old)
        self.assertIs(h.write_record,baseline)
        self.assertEqual(result,(note,'diagnosis'))
        self.assertEqual(len(requests),1)
        self.assertTrue(requests[0][0]['content'].endswith(SYSTEM))
        self.assertEqual(rag_graph.LAST_RUN['nodes'],['context','plan_and_retrieve','generate','audit'])
        self.assertEqual(rag_graph.LAST_RUN['audit']['selected_count'],0)
        self.assertTrue(rag_graph.LAST_RUN['audit']['has_soap'])

    def test_compiled_runtime_uses_no_checkpointer(self):
        from nova_agent.rag_graph import validate_runtime
        compiled=validate_runtime()
        self.assertIsNone(compiled.checkpointer)
