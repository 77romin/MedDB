import json
from pathlib import Path
import tempfile
import unittest
from meddb import KB
from meddb.workflow import profile_kb, resource


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kb=KB()

    def test_negation_scope_and_insomnia(self):
        result=self.kb.normalize('열이 없어요; 기침이 있어요; 잠을 못 자요')
        states={m['candidate_ids'][0]:m['proposed_state'] for m in result['mentions']}
        self.assertEqual(states,{'nova:fever':'absent','hpo:HP:0012735':'present','hpo:HP:0100785':'present'})
        self.assertTrue(all(m['needs_confirmation'] for m in result['mentions']))

    def test_history_and_ambiguous_negation(self):
        for text in ('예전에 기침이 있었어요','어머니가 기침해요','발열과 기침은 없어요','기침이 없지는 않아요'):
            result=self.kb.normalize(text)
            self.assertTrue(result['mentions'])
            self.assertTrue(all(m['proposed_state']=='unknown' for m in result['mentions']))

    def test_contradictory_statements(self):
        result=self.kb.normalize('기침이 있어요; 기침은 없어요')
        self.assertEqual(result['conflicts'],['hpo:HP:0012735'])
        self.assertTrue(all(m['proposed_state']=='unknown' for m in result['mentions']))

    def test_duration_preserved_not_converted_to_rule(self):
        result=self.kb.normalize('기침이 3일 지속돼요')
        self.assertEqual(result['mentions'][0]['duration_mentions'],['3일'])

    def test_longest_phrase_does_not_double_count(self):
        result=self.kb.normalize('상복부 통증이 있어요')
        self.assertEqual([m['candidate_ids'] for m in result['mentions']],[['nova:upper-abdominal-pain']])

    def test_profiles_explicit_and_preserve_original(self):
        before=len(self.kb.data['assertions'])
        view,policy=profile_kb(self.kb,'pilot')
        self.assertEqual(policy['assertions'],50)
        self.assertTrue(all(a['source_id'].startswith('niddk-') for a in view.data['assertions']))
        self.assertEqual(len(self.kb.data['assertions']),before)
        result=self.kb.suggest({'nova:vomiting':'present'})
        self.assertEqual(result['ranking']['candidates'],[])
        self.assertEqual(result['checklists'],[])

    def test_recommendation_evidence_and_known_exclusion(self):
        obs={'nova:vomiting':'present','nova:fever':'absent'}
        result=self.kb.suggest(obs,'pilot')
        self.assertTrue(result['recommendations'])
        self.assertTrue(all(r['finding'] not in obs for r in result['recommendations']))
        self.assertTrue(all(r['evidence'] for r in result['recommendations']))
        self.assertTrue(all(r['requires_clinical_review'] for r in result['recommendations']))

    def test_templates_fit_say_limit(self):
        dictionary,_=resource('actions.json')
        for entry in dictionary['entries']:
            if entry['action']=='SAY':self.assertLessEqual(len(entry['content']),30)

    def test_real_excluded_no_positive_match(self):
        a=next(a for a in self.kb.data['assertions'] if a.get('frequency_label')=='EXCLUDED')
        result=self.kb.rank({a['object']:'present'},True,100)
        self.assertFalse(any(c['disease']['id']==a['subject'] for c in result['candidates']))

    def test_checklist_does_not_assert_diagnosis(self):
        result=self.kb.suggest({'hpo:HP:0100785':'present'},'research')
        self.assertEqual(result['checklists'][0]['id'],'sleep-medication-history')
        self.assertNotIn('diagnosis',result['checklists'][0])

    def test_three_arm_logs_use_paired_cases(self):
        from tools.evaluate_agent_knowledge import evaluate_logs
        rows=[{'arm':arm,'case_id':'A','correct':True,'turns':3} for arm in ('no_kb','previous_kb','improved_kb')]
        rows.append({'arm':'improved_kb','case_id':'B','correct':False})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'logs.json';path.write_text(json.dumps(rows),encoding='utf-8')
            report=evaluate_logs(path)
        self.assertEqual(report['paired_cases'],1)
        self.assertEqual(report['arms']['improved_kb']['accuracy'],1)
        self.assertEqual(report['unpaired_cases']['improved_kb'],['B'])

    def test_agent_tool_interfaces(self):
        self.assertIn('mentions',self.kb.call('normalize',{'text':'발열'})['result'])
        self.assertIn('recommendations',self.kb.call('suggest',{'observations':{'nova:fever':'present'},'profile':'pilot'})['result'])


if __name__=='__main__':unittest.main()
