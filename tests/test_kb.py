import copy
import json
import tempfile
import unittest
from pathlib import Path
from meddb import KB

class KnowledgeTests(unittest.TestCase):
    def setUp(self): self.kb = KB(version="meddb-2026.10.10.3")
    def test_drafts_excluded_by_default(self):
        self.assertEqual(self.kb.rank({'nova:fever':'present'})['candidates'], [])
        self.assertEqual(self.kb.graph('nova:acute-pancreatitis')['assertions'], [])
    def test_unknown_and_absence_are_separate(self):
        obs={'nova:upper-abdominal-pain':'present','nova:fever':'unknown'}
        c=self.kb.rank(obs,True)['candidates'][0]
        self.assertEqual(c['conflicts'],[])
        obs['nova:fever']='absent'
        self.assertEqual(next(c for c in self.kb.rank(obs,True)['candidates'] if c['disease']['id']=='nova:acute-pancreatitis')['conflicts'],['nova:fever'])
    def test_evidence_preserved(self):
        c=self.kb.rank({'nova:vomiting':'present'},True)['candidates'][0]
        self.assertTrue(all(a['source_id'] and a['locator'] and a['review_status']=='draft' for a in c['evidence']))
    def test_rank_limit_preserves_total(self):
        result=self.kb.rank({'nova:vomiting':'present'},True,limit=1)
        self.assertEqual(len(result['candidates']),1)
        self.assertGreater(result['total_candidates'],1)
        with self.assertRaises(ValueError):self.kb.rank({},limit=0)
    def test_invalid_input(self):
        for obs in ({'bad':'present'},{'nova:gallstones':'present'},{'nova:fever':'maybe'}):
            with self.assertRaises(ValueError): self.kb.rank(obs)
    def test_dangling_and_unreviewed_claims_rejected(self):
        for field,value in [('source_id','missing'),('object','missing'),('review_status','reviewed')]:
            data=copy.deepcopy(self.kb.data);data['assertions'][0][field]=value
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'data.json';p.write_text(json.dumps(data))
                with self.assertRaises(ValueError): KB(p)
    def test_rejected_excluded_even_in_draft_mode(self):
        self.kb.data['assertions'][0]['review_status']='rejected'
        self.assertNotIn('assertion:001',[a['id'] for a in self.kb.assertions(True)])
    def test_versions_are_fixed(self):
        old=KB(version='meddb-2026.10.10.1')
        new=KB(version='meddb-2026.10.10.2')
        self.assertEqual(len(old.search('', 'Disease')),2)
        self.assertEqual(len(new.search('', 'Disease')),9)
        self.assertNotEqual(old.sha256,new.sha256)
        with self.assertRaises(ValueError): KB(version='../bad')
    def test_specific_findings_distinguish_candidates(self):
        c=self.kb.rank({'nova:rlq-migration':'present','nova:vomiting':'present'},True)['candidates'][0]
        self.assertEqual(c['disease']['id'],'nova:appendicitis')
    def test_rdf_claims_preserve_drafts(self):
        from meddb.rdf import export
        self.assertNotIn('a nova:Assertion',export(self.kb))
        rdf=export(self.kb,True)
        self.assertEqual(rdf.count('a nova:Assertion'),50)
        self.assertIn('nova:reviewStatus "draft"',rdf)
        self.assertNotIn('> nova:has_phenotype <',rdf)
    def test_tool_result_has_version(self):
        result=self.kb.call('search',{'text':'맹장염'})
        self.assertEqual(result['result'][0]['id'],'nova:appendicitis')
        self.assertEqual(result['version'],self.kb.version)
        with self.assertRaises(ValueError): self.kb.call('validate',{})
if __name__=='__main__': unittest.main()
