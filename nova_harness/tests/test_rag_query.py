import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nova_agent.rag_query import QueryStore,validate

EVIDENCE=[{'id':'initial','content':'환자는 최근 수면제를 복용했다고 합니다.'}]


def plan():
    return {'query':'sedative hypnotic dependence withdrawal safety taper', 'intent':'safety',
            'clinical_question':'약물 사용 시 안전한 치료 방향은 무엇인가?',
            'patient_evidence':[{'id':'initial','quote':'최근 수면제를 복용'}]}


class QueryTests(unittest.TestCase):
    def modules(self,seconds=1000):
        return {'examples':SimpleNamespace(hybrid_agent=SimpleNamespace(parse_json=json.loads)),
                'examples.consult_skeleton':SimpleNamespace(seconds_left=lambda s:seconds)}

    def test_provenance_and_abstention(self):
        query,audit=validate(plan(),EVIDENCE)
        self.assertIn('withdrawal',query)
        self.assertEqual(audit['patient_evidence_ids'],['initial'])
        self.assertEqual(validate({'query':''},EVIDENCE),('',{}))

    def test_invalid_queries_and_fabricated_observation_rejected(self):
        invalid=[]
        p=plan();p['patient_evidence'][0]['id']='doctor_question';invalid.append(p)
        p=plan();p['patient_evidence'][0]['quote']='임신 중입니다';invalid.append(p)
        p=plan();p['query']='x'*241;invalid.append(p)
        p=plan();p['query']='line1\nline2';invalid.append(p)
        p=plan();p['intent']='prescribe';invalid.append(p)
        p=plan();p['patient_evidence']=[];invalid.append(p)
        invalid.append(None)
        for p in invalid:
            with self.subTest(payload=p),self.assertRaises(ValueError):validate(p,EVIDENCE)

    def test_one_call_cache_and_changed_observations_use_baseline(self):
        calls=[];queries=[]
        def chat(messages,**kwargs):
            calls.append(messages);return {'choices':[{'message':{'content':json.dumps(plan())}}]}
        def search(q,k):queries.append(q);return [{'chunk_id':'d1'}]
        store=QueryStore(SimpleNamespace(search=search))
        store.context=(SimpleNamespace(chat=chat,session=lambda:{}),EVIDENCE)
        with patch.dict('sys.modules',self.modules()):
            store.search('baseline');store.search('baseline')
            self.assertEqual(len(calls),1)
            self.assertEqual(queries,[plan()['query']]*2)
            store.context=(store.context[0],EVIDENCE+[{'id':'new','content':'복용약이 바뀌었다고 답함'}])
            store.search('baseline')
            self.assertEqual(queries[-1],'baseline')
            self.assertEqual(len(calls),1)

    def test_no_results_returns_to_original_query(self):
        queries=[]
        def search(q,k):queries.append(q);return [] if q!='baseline' else [{'chunk_id':'original'}]
        client=SimpleNamespace(session=lambda:{},chat=lambda *a,**k:{'choices':[{'message':{'content':json.dumps(plan())}}]})
        store=QueryStore(SimpleNamespace(search=search));store.context=(client,EVIDENCE)
        with patch.dict('sys.modules',self.modules()):
            self.assertEqual(store.search('baseline'),[{'chunk_id':'original'}])
        self.assertEqual(queries,[plan()['query'],'baseline'])

    def test_deadline_and_model_failure_preserve_baseline(self):
        calls=[]
        def chat(*a,**k):calls.append(1);raise TimeoutError()
        client=SimpleNamespace(session=lambda:{},chat=chat)
        for seconds in (329,1000):
            queries=[]
            def search(q,k):queries.append(q);return []
            store=QueryStore(SimpleNamespace(search=search));store.context=(client,EVIDENCE)
            with patch.dict('sys.modules',self.modules(seconds)):
                self.assertEqual(store.search('baseline'),[])
            self.assertEqual(queries,['baseline'])
        self.assertEqual(len(calls),1)
