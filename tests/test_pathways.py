import unittest
from meddb import KB
from meddb.pathways import recommend


class PathwayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kb=KB()

    def test_draft_is_opt_in(self):
        self.assertEqual(recommend(self.kb,{'hpo:HP:0100785':'present'})['pathways'],[])

    def test_confirmed_history_stops_repeated_questions(self):
        result=recommend(self.kb,{'hpo:HP:0100785':'present'},{'medication-details':{'status':'confirmed','value':'patient reported medication details','evidence_id':'event-2'}},True)
        self.assertNotIn('medication-details',[r['id'] for r in result['pathways'][0]['pending']])
        with self.assertRaises(ValueError):recommend(self.kb,{}, {'medication-details':{'status':'confirmed','value':'answer'}},True)

    def test_child_puberty_context_does_not_affect_score(self):
        context={'age':6,'sex':'male','puberty_assessment':'not_age_appropriate'}
        base=self.kb.rank({'hpo:HP:0004322':'present'},True,patient=context)
        result=self.kb.rank({'hpo:HP:0004322':'present','hpo:HP:0000823':'absent'},True,patient=context)
        self.assertEqual([(r['disease']['id'],r['score']) for r in base['candidates']],[(r['disease']['id'],r['score']) for r in result['candidates']])
        self.assertEqual(result['context_ignored'],['hpo:HP:0000823'])
        proposed=self.kb.suggest({'hpo:HP:0004322':'present'},'research',patient=context)
        self.assertNotIn('hpo:HP:0000823',[r['finding'] for r in proposed['recommendations']])

    def test_no_automatic_age_threshold_or_diagnosis(self):
        result=recommend(self.kb,{'hpo:HP:0004322':'present'},include_draft=True)
        self.assertEqual(result['pathways'][0]['id'],'child-growth')
        self.assertTrue(all('diagnosis' not in r for r in result['pathways'][0]['pending']))

    def test_context_only_does_not_claim_age_fields_were_supplied(self):
        result=self.kb.rank({},True,patient={'puberty_assessment':'not_age_appropriate'})
        self.assertFalse(any(w.startswith('No reviewed age') for w in result['warnings']))
