import unittest

from meddb import MedDB
from examples.hybrid_agent import Tracker, write_record
from examples.consult_skeleton import read_answer, read_exam


class Client:
    def __init__(self, record=None):
        import json
        self.output = json.dumps(record or {}, ensure_ascii=False)

    def chat(self, *args, **kwargs):
        return {'choices': [{'message': {'content': self.output}}]}


class ClinicalSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = MedDB.open()

    def test_unknown_does_not_become_absence(self):
        result = self.db.match_findings('발열이 있는지 모르겠어요')
        self.assertIn('fever', result['unknown'])
        self.assertNotIn('fever', result['absent'])
        self.assertEqual(read_answer(None, '열이 있나요?', '모르겠어요', '발열'), '?')

    def test_partial_exam_leaves_unmentioned_findings_unknown(self):
        findings = [self.db.findings[f] for f in self.db.exam_findings['ex_abd_palp']]
        result = read_exam(None, '우하복부 압통(-)', findings)
        self.assertEqual(result['rlq_tenderness'], '-')
        self.assertEqual(result['rebound_guarding'], '?')
        self.assertEqual(result['pulsatile_mass'], '?')

    def test_completed_exam_does_not_confirm_findings(self):
        self.assertEqual(self.db._known([], [], ['ex_abd_palp']), set())
        self.assertEqual(self.db._known(['rlq_tenderness'], [], ['ex_abd_palp']), {'rlq_tenderness'})

    def test_contradiction_requires_reconfirmation_and_keeps_history(self):
        tracker = Tracker(self.db, 'chest_pain', 58, 'M', '', {})
        tracker.mark('fever', '+', 1)
        tracker.mark('fever', '-', 2)
        self.assertNotIn('fever', tracker.present)
        self.assertNotIn('fever', tracker.absent)
        self.assertIn('fever', tracker.conflicts)
        self.assertIn('fever', tracker.unknown)
        self.assertEqual([e['turn'] for e in tracker.events], [1, 2])
        self.assertEqual(tracker.turns['fever'], 2)

    def test_changed_diagnosis_regenerates_assessment_and_plan(self):
        tracker = Tracker(self.db, 'chest_pain', 58, 'M', '', {})
        record = {'S': {'cc': '흉통'}, 'diagnosis': '공황발작'}
        note, diagnosis = write_record(Client(record), self.db, tracker, '가슴이 아파요', {}, [])
        self.assertEqual(diagnosis, '공황발작')
        self.assertTrue(note['A']['evidence'].startswith('#1. 공황발작'))
        self.assertNotIn('양성자펌프억제제', note['P']['treatment'])

    def test_outside_kb_diagnosis_cannot_inherit_old_plan(self):
        tracker = Tracker(self.db, 'chest_pain', 58, 'M', '', {})
        note, diagnosis = write_record(Client({'S': {'cc': '흉통'}, 'diagnosis': '미등록 진단 XYZ'}),
                                       self.db, tracker, '', {}, [])
        self.assertEqual(note['A']['evidence'], '#1. ' + diagnosis)
        self.assertTrue(all(not value for value in note['P'].values()))


if __name__ == '__main__':
    unittest.main()
