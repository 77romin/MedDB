import json
import unittest

from nova_agent.clinical import ClinicalAdvisor, demographics
from nova_agent.runtime import prepare, consult
from nova_agent.state import PatientState
from nova_agent.config import Config
from test_harness import ScriptClient


class ClinicalTests(unittest.TestCase):
    def advisor(self, opening='잠을 잘 못 자 수면제를 원합니다.'):
        return ClinicalAdvisor(prepare()['clinical_graph'],opening)

    def state(self, a):
        return PatientState({}, {c['id']:c for c in a.concepts()})

    def test_no_patient_identifier_routing(self):
        self.assertEqual(self.advisor().complaint['id'],'insomnia')
        self.assertEqual(self.advisor('이름은 아무개이고 키가 작아요.').complaint['id'],'short_stature')
        self.assertIsNone(self.advisor('알 수 없는 새 증상입니다.').complaint)

    def test_child_age_precedes_caregiver(self):
        self.assertEqual(demographics('여섯 살 남자아이. 엄마는 서른일곱 살이다.'),(6,'M'))

    def test_child_not_routinely_sent_for_puberty_exam(self):
        a=self.advisor('여섯 살 남자아이. 키가 작아요.'); s=self.state(a)
        self.assertFalse(any(x['target']=='meddb:ex_tanner' for x in a.context(s)['actions']))

    def test_attempt_is_not_confirmation(self):
        a=self.advisor();s=self.state(a)
        s.add_response('SAY','수면제를 드시고 계신가요?',{'content':'모르겠어요'},'meddb:hypnotic_use')
        c=a.context(s)
        self.assertFalse(any(x['target']=='meddb:hypnotic_use' for x in c['actions']))
        self.assertTrue(any('hypnotic_use' in x['missing'] for x in c['hypotheses']))

    def test_conflicting_findings_not_used_to_rank(self):
        a=self.advisor();s=self.state(a)
        for assertion in ['present','absent']:
            s.facts.append({'concept_id':'meddb:hypnotic_use','assertion':assertion})
        self.assertIn('hypnotic_use',a.context(s)['conflicts'])

    def test_physical_signs_require_exam(self):
        a=self.advisor();s=self.state(a)
        sign=next(c for c in a.concepts() if c['kind']=='sign')
        s.add_response('SAY','어떤가요?',{'content':'정상'})
        fact={'concept_id':sign['id'],'evidence_id':'e1','quote':'정상','assertion':'absent'}
        self.assertFalse(s.accept_facts([fact])[0])
        s.add_response('EXAM','진찰합니다',{'result':'정상'})
        fact['evidence_id']='e2';self.assertTrue(s.accept_facts([fact])[0])

    def test_full_closing_sends_and_records_actual_sent_messages(self):
        initial={'diagnosis':'추가 평가 필요','evidence_ids':['initial'],'plan':{'education':'추가 평가 계획'}}
        sentences={'assessment':'원인 확인을 위한 추가 평가가 필요해요.', 'plan':'검사 계획을 함께 정하겠습니다.',
                   'follow_up':'결과를 확인할 재진을 잡겠습니다.', 'safety_net':'갑자기 악화되면 바로 진료받으세요.', 'concern':'걱정을 함께 살펴보겠습니다.'}
        c=ScriptClient([{'next_action':{'type':'DONE'}},initial,initial,sentences,initial],['걱정돼요']+['네']*6)
        result=consult(c,prepare(),Config(max_turns=10))
        self.assertEqual(result['status'],'completed')
        self.assertIn('실제 SAY 설명:',c.submitted['note']['P']['education'])
        self.assertIn('어떻게 하실지',c.submitted['note']['S']['hpi'])
        self.assertLessEqual(50-c.turns,10)

    def test_overlong_closing_never_sent_or_claimed(self):
        initial={'diagnosis':'미정'}
        c=ScriptClient([{'next_action':{'type':'DONE'}},initial,initial,{'assessment':'가'*31},{},initial],['모르겠어요','네'])
        consult(c,prepare(),Config(max_turns=10))
        self.assertNotIn('가'*31,json.dumps(c.submitted,ensure_ascii=False))

    def test_graph_has_no_case_answers_or_automatic_treatment(self):
        graph=prepare()['clinical_graph']
        self.assertEqual(len(graph['complaints']),19)
        for row in graph['diseases']:
            self.assertNotIn('plan',row)
            self.assertNotIn('accepted_diagnoses',row)


if __name__=='__main__':unittest.main()
