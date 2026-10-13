import unittest
from meddb import KB, MedDB
from meddb.bridge import KnowledgeBridge
from examples.hybrid_agent import Tracker


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clinical, cls.reference = MedDB.open(), KB()
        cls.bridge = KnowledgeBridge(cls.clinical, cls.reference)

    def test_draft_mapping_requires_research_opt_in(self):
        tracker = Tracker(self.clinical, 'cough', 40, 'M', '기침이 있어요', {})
        reviewed = self.bridge.support(tracker)
        self.assertEqual(reviewed['mappings_used'], [])
        research = self.bridge.support(tracker, 'research')
        self.assertEqual(research['reference']['observations'][0]['finding_id'], 'hpo:HP:0012735')
        self.assertEqual(research['mappings_used'][0]['review_status'], 'draft')
        self.assertEqual(research['reference']['observations'][0]['state'], 'present')

    def test_unknown_survives_translation(self):
        tracker = Tracker(self.clinical, 'cough', 40, 'M', '발열은 모르겠어요', {})
        result = self.bridge.support(tracker, 'research')
        self.assertEqual(result['reference']['observations'][0]['state'], 'unknown')

    def test_no_source_content_means_no_confirmed_translation(self):
        tracker = Tracker(self.clinical, 'cough', 40, 'M', '', {})
        tracker.mark('fever', '+', 1)
        self.assertEqual(self.bridge.support(tracker, 'research')['reference']['observations'], [])

    def test_mapping_validation_rejects_unknown_endpoints(self):
        with self.assertRaises(ValueError):
            KnowledgeBridge(self.clinical, self.reference, {'version': 'test', 'mappings': [
                {'clinical_id': 'missing', 'finding_id': 'nova:fever', 'relation': 'exact', 'review_status': 'draft'}]})

    def test_submission_allowlist_excludes_evaluation(self):
        from tools.make_submission import reference_files, validate_members
        files = reference_files()
        validate_members(files)
        self.assertFalse(any('evaluation' in name for name in files))
        with self.assertRaises(ValueError):
            validate_members(['data/agent/evaluation-cases.json'])

    def test_same_scripted_agent_runs_all_knowledge_modes(self):
        from test_meddb import ScriptedLLM
        from examples.hybrid_agent import consult
        for mode in ('clinical', 'ontology', 'integrated'):
            with self.subTest(mode=mode):
                client = ScriptedLLM('40세 남자입니다. 기침이 있어요.', [{'action': 'DONE'}],
                                     {'S': {'cc': '기침'}, 'diagnosis': '급성 기관지염'})
                consult(client, self.clinical, knowledge_mode=mode, reference_profile='research')
                self.assertIsNotNone(client.submitted)
                hints = '\n'.join(client.prompts)
                self.assertEqual('[온톨로지 참고 근거' in hints, mode != 'clinical')
                if mode == 'ontology':
                    self.assertNotIn('[추천 행동]', hints)


if __name__ == '__main__':
    unittest.main()
