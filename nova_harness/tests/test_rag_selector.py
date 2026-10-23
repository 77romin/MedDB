from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nova_agent.rag_selector import observations, validate, SelectorStore

DOCS=[{'chunk_id':'d1','excerpt':'Adult patients with confirmed asthma should receive follow-up.'}]
EVIDENCE=[{'id':'initial','content':'성인 환자로 천식 증상이 있습니다.'}]


def decision(status='usable'):
    return {'decisions':[{'chunk_id':'d1','status':status,'reason':'대상과 근거를 대조함',
                         'patient_evidence':[{'id':'initial','quote':'성인 환자'}],
                         'source_quote':'Adult patients with confirmed asthma'}]}


class SelectorTests(unittest.TestCase):
    def test_observations_never_promote_doctor_question(self):
        result=observations('시작',{},['의사: 임신 중이세요?','환자: 몰라요','진찰(호흡): 정상'])
        self.assertEqual([r['id'] for r in result],['initial','vitals','t1','t2'])
        self.assertEqual(result[2]['content'],'몰라요')
        self.assertEqual(result[2]['question_context'],'의사: 임신 중이세요?')

    def test_subset_and_no_model_rewritten_document(self):
        payload=decision();payload['decisions'][0]['invented_patient_age']=99
        accepted,audit=validate(payload,DOCS,EVIDENCE)
        self.assertIs(accepted[0],DOCS[0])
        self.assertNotIn('invented_patient_age',accepted[0])
        for status in ('rejected','uncertain'):
            self.assertEqual(validate(decision(status),DOCS,EVIDENCE)[0],[])

    def test_unknown_id_fabricated_quotes_missing_duplicate_fail_closed(self):
        variants=[]
        p=decision();p['decisions'][0]['chunk_id']='invented';variants.append(p)
        p=decision();p['decisions'][0]['patient_evidence'][0]['quote']='소아 환자';variants.append(p)
        p=decision();p['decisions'][0]['source_quote']='Invented recommendation.';variants.append(p)
        p=decision();p['decisions'][0]['patient_evidence']=[];variants.append(p)
        p=decision();p['decisions'].append(deepcopy(p['decisions'][0]));variants.append(p)
        variants.extend([{'decisions':[]},{},None])
        for payload in variants:
            with self.subTest(payload=payload),self.assertRaises(ValueError):validate(payload,DOCS,EVIDENCE)

    def modules(self, seconds=1000):
        return {'examples':SimpleNamespace(hybrid_agent=SimpleNamespace(parse_json=json.loads)),
                'examples.consult_skeleton':SimpleNamespace(seconds_left=lambda session:seconds)}

    def test_cache_changed_observation_cap_and_deadline(self):
        calls=[]
        def chat(messages,**kwargs):
            calls.append(messages)
            return {'choices':[{'message':{'content':json.dumps(decision())}}]}
        client=SimpleNamespace(chat=chat,session=lambda:{})
        store=SelectorStore(SimpleNamespace(search=lambda *a,**kw:DOCS))
        store.context=(client,EVIDENCE)
        with patch.dict('sys.modules',self.modules()):
            self.assertEqual(store.search('asthma'),DOCS)
            self.assertEqual(store.search('asthma'),DOCS)
            self.assertEqual(len(calls),1)
            store.context=(client,EVIDENCE+[{'id':'new','content':'새 관찰 하나'}])
            self.assertEqual(store.search('asthma'),DOCS)
            store.context=(client,EVIDENCE+[{'id':'another','content':'새 관찰'}])
            self.assertEqual(store.search('asthma'),[])
            self.assertEqual(len(calls),2)
        fresh=SelectorStore(store.store);fresh.context=(client,EVIDENCE)
        with patch.dict('sys.modules',self.modules(seconds=239)):
            self.assertEqual(fresh.search('asthma'),[])
            self.assertEqual(fresh.attempts,0)

    def test_model_failure_is_not_retried_or_forwarded(self):
        def chat(*args,**kwargs):raise TimeoutError('no response')
        client=SimpleNamespace(chat=chat,session=lambda:{})
        store=SelectorStore(SimpleNamespace(search=lambda *a,**kw:DOCS));store.context=(client,EVIDENCE)
        with patch.dict('sys.modules',self.modules()):
            self.assertEqual(store.search('asthma'),[])
            self.assertEqual(store.search('asthma'),[])
        self.assertEqual(store.attempts,1)
        self.assertEqual(store.events[0]['error_type'],'TimeoutError')
