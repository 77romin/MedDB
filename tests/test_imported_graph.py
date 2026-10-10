import unittest
from meddb import KB

class ImportedGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.kb=KB()
    def test_dismech_import_preserves_provenance(self):
        imported=[a for a in self.kb.data['assertions'] if a['extraction_method']=='upstream_import']
        self.assertGreater(len(imported),1000)
        self.assertTrue(all(a['review_status']=='draft' and a['locator'] and a['source_id'] in self.kb.sources for a in imported))
    def test_directed_mechanism_exploration(self):
        disease=next(n for n in self.kb.nodes.values() if n['kind']=='Disease' and 'wilson' in n['label_en'].lower())
        g=self.kb.graph(disease['id'],True,2,'out','DisMech')
        self.assertTrue(any(n['kind']=='Mechanism' for n in g['nodes']))
        self.assertTrue(all(a['source_id'].startswith('dismech:') for a in g['assertions']))
        self.assertEqual([n['id'] for n in g['nodes'] if n['kind']=='Disease'],[disease['id']])
    def test_reversed_finding_reaches_diseases(self):
        g=self.kb.graph('nova:fever',True,1,'in')
        self.assertTrue(any(n['kind']=='Disease' for n in g['nodes']))
        self.assertTrue(all(a['object']=='nova:fever' for a in g['assertions']))
    def test_no_drafts_in_default_api(self):
        self.assertEqual(self.kb.graph('nova:fever',direction='in')['assertions'],[])
