import unittest
from meddb import KB


class TargetedReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kb=KB(version='meddb-2026.10.13.1')

    def test_new_relations_remain_draft(self):
        rows=[a for a in self.kb.data['assertions'] if a['id'].startswith('nova-targeted:')]
        self.assertEqual(len(rows),4)
        self.assertTrue(all(a['review_status']=='draft' and a['source_id'] in self.kb.sources and a['locator'] for a in rows))
        self.assertTrue(all(not self.kb.sources[a['source_id']]['url'].startswith('https://nova.snubhai.org') for a in rows))

    def test_old_release_does_not_change(self):
        old=KB(version='meddb-2026.10.10.4')
        self.assertNotIn('nova:constitutional-growth-delay',old.nodes)
        self.assertEqual(len(old.data['assertions']),114088)

    def test_new_disease_search_and_review_policy(self):
        self.assertEqual(self.kb.search('Sedative-Hypnotic Use Disorder','Disease')[0]['id'],'nova:sedative-hypnotic-use-disorder')
        self.assertEqual(self.kb.rank({'nova:sedative-craving':'present'})['candidates'],[])
        result=self.kb.suggest({'nova:sedative-craving':'present'},'research')
        self.assertEqual(result['ranking']['candidates'][0]['disease']['id'],'nova:sedative-hypnotic-use-disorder')
        self.assertIn('Draft medical relationships included.',result['ranking']['warnings'])
