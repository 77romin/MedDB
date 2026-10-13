import unittest
from meddb import KB
from examples.knowledge_session import KnowledgeSession


class AssistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kb=KB()

    def test_provenance_required_and_question_not_evidence(self):
        obs=[{'finding_id':'nova:fever','state':'absent'}]
        with self.assertRaises(ValueError):self.kb.assist(obs,[])
        with self.assertRaises(ValueError):self.kb.assist(obs,[{'id':'q','kind':'question','turn':1,'content':'열이 나나요?'}])

    def test_missing_and_duplicate_events_rejected(self):
        event={'id':'e','kind':'say','turn':1,'content':'열은 없어요'}
        obs=[{'finding_id':'nova:fever','state':'absent','evidence_ids':['missing']}]
        with self.assertRaises(ValueError):self.kb.assist(obs,[event])
        with self.assertRaises(ValueError):self.kb.assist([], [event,event])

    def test_preliminary_test_results_rejected(self):
        event={'id':'t','kind':'test','turn':1,'content':'TSH result'}
        with self.assertRaises(ValueError):self.kb.assist([], [event])
        self.assertEqual(self.kb.assist([], [event],phase='final')['phase'],'final')

    def test_context_provenance_required(self):
        with self.assertRaises(ValueError):self.kb.assist([],[],patient={'age':6})

    def test_actual_session_adapter_and_history(self):
        session=KnowledgeSession(self.kb,profile='research')
        event=session.record_result('say',1,'잠을 잘 못 자요')
        session.confirm_observation('hpo:HP:0100785','present',[event])
        medication=session.record_result('say',2,'약명·회당 용량·횟수·처방 출처를 답변함')
        session.complete_history('medication-details','약명·용량·횟수·출처를 모두 확인함',medication)
        result=session.support()
        self.assertEqual(result['contract_version'],'nova-knowledge-contract-1')
        self.assertNotIn('medication-details',[r['id'] for p in result['history_pathways']['pathways'] for r in p['pending']])
        self.assertEqual(result['observations'][0]['evidence_ids'],[event])

    def test_unknown_observation_needs_no_fabricated_event(self):
        result=self.kb.assist([{'finding_id':'nova:fever','state':'unknown'}],[])
        self.assertEqual(result['observations'][0]['confirmation'],'unconfirmed')

    def test_tool_contract_available(self):
        result=self.kb.call('assist',{'observations':[],'events':[]})
        self.assertEqual(result['result']['contract_version'],'nova-knowledge-contract-1')
