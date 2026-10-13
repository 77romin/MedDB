import unittest
from tools.build_public_checklists import build_report
from meddb import KB


class PublicChecklistTests(unittest.TestCase):
    def test_missing_pathway_is_not_reported_complete(self):
        config={'scope':'evaluation only','cases':[{'case_id':'test','disease_id':'nova:appendicitis','patient_context':{},'source':'fixture','items':[{'id':'missing','pathway':'not-built'}]}]}
        report=build_report(KB(version='meddb-2026.10.10.3'),config)
        self.assertEqual(report['cases'][0]['items'][0]['status'],'missing_pathway')
