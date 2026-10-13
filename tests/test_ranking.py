import copy
import unittest
from meddb import KB


class EvidenceRankingTests(unittest.TestCase):
    def setUp(self):
        self.kb = KB(version='meddb-2026.10.10.3')

    def test_excluded_present_is_counter_evidence(self):
        row = next(a for a in self.kb.data['assertions'] if a['subject'] == 'nova:acute-pancreatitis' and a['object'] == 'nova:fever')
        row['frequency_label'] = 'EXCLUDED'
        result = self.kb.rank({'nova:upper-abdominal-pain':'present', 'nova:fever':'present'}, True)
        candidate = next(c for c in result['candidates'] if c['disease']['id']=='nova:acute-pancreatitis')
        self.assertIn('nova:fever', candidate['conflicts'])
        self.assertNotIn('nova:fever', candidate['matched'])
        absent = self.kb.rank({'nova:upper-abdominal-pain':'present', 'nova:fever':'absent'}, True)
        other = next(c for c in absent['candidates'] if c['disease']['id']=='nova:acute-pancreatitis')
        self.assertGreater(other['score'], candidate['score'])

    def test_duplicate_assertion_does_not_change_score(self):
        before = self.kb.rank({'nova:vomiting':'present'}, True)
        self.kb.data['assertions'].append(copy.deepcopy(self.kb.data['assertions'][0]))
        after = self.kb.rank({'nova:vomiting':'present'}, True)
        self.assertEqual([(c['disease']['id'], c['score']) for c in before['candidates']], [(c['disease']['id'],c['score']) for c in after['candidates']])

    def test_unknown_does_not_change_score(self):
        a = self.kb.rank({'nova:vomiting':'present'}, True)
        b = self.kb.rank({'nova:vomiting':'present','nova:fever':'unknown'}, True)
        self.assertEqual(a['candidates'], b['candidates'])

    def test_conditions_without_rules_are_explicit(self):
        result = self.kb.rank({'nova:vomiting':'present'}, True, patient={'age':30,'sex':'female'})
        self.assertTrue(any(w.startswith('No reviewed') for w in result['warnings']))
        self.assertEqual(result['filtered'], [])
        for patient in ({'age':True},{'age':float('nan')},{'age':-1},{'sex':'bad'}):
            with self.assertRaises(ValueError):self.kb.rank({}, patient=patient)

    def test_only_reviewed_conditions_filter(self):
        disease = self.kb.nodes['nova:acute-pancreatitis']
        disease['clinical_constraints'] = {'max_age':10,'review_status':'draft','reviewer':'test','source_id':next(iter(self.kb.sources)),'locator':'test fixture'}
        obs = {'nova:upper-abdominal-pain':'present'}
        self.assertTrue(any(c['disease']['id']==disease['id'] for c in self.kb.rank(obs,True,patient={'age':30})['candidates']))
        disease['clinical_constraints']['review_status'] = 'reviewed'
        result = self.kb.rank(obs,True,patient={'age':30})
        self.assertFalse(any(c['disease']['id']==disease['id'] for c in result['candidates']))
        self.assertEqual(result['filtered'][0]['disease_id'], disease['id'])

    def test_contradictory_source_polarity_is_not_scored(self):
        row = copy.deepcopy(next(a for a in self.kb.data['assertions'] if a['subject']=='nova:acute-pancreatitis' and a['object']=='nova:fever'))
        row['frequency_label'] = 'EXCLUDED'
        self.kb.data['assertions'].append(row)
        result = self.kb.rank({'nova:upper-abdominal-pain':'present','nova:fever':'present'},True)
        c = next(c for c in result['candidates'] if c['disease']['id']=='nova:acute-pancreatitis')
        self.assertIn('nova:fever',c['uncertain'])
        self.assertNotIn('nova:fever',c['matched'])

    def test_category_filter(self):
        self.kb.nodes['nova:acute-pancreatitis']['category']='test-category'
        result = self.kb.rank({'nova:upper-abdominal-pain':'present'},True,category='test-category')
        self.assertEqual([c['disease']['id'] for c in result['candidates']],['nova:acute-pancreatitis'])


if __name__ == '__main__':
    unittest.main()
