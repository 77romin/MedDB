import unittest

from nova_agent.clinical import ClinicalAdvisor
from nova_agent.coverage import CoveragePlanner
from nova_agent.runtime import prepare, consult
from nova_agent.state import PatientState
from nova_agent.config import Config
from nova_agent.records import make_record, normalize_assessment
from test_harness import ScriptClient


class CoverageTests(unittest.TestCase):
    def test_objective_exams_are_visible_before_history_queue_is_exhausted(self):
        a,s,c=self.setup_case()
        actions=a.context(s)['actions']
        self.assertLessEqual(len(actions),8)
        self.assertEqual(sum(x['type']=='EXAM' for x in actions),2)

    def test_declared_core_target_uses_canonical_single_action(self):
        _,_,c=self.setup_case()
        proposal={'type':'EXAM','target':'meddb:ex_mental','content':'정신 상태를 보겠습니다.'}
        action,event=c.choose(proposal,45,12)
        self.assertEqual(action['content'],'의식·지남력 평가를 하겠습니다.')
        self.assertEqual(event['reason'],'canonical_target_action')

    def test_valid_core_choice_is_not_displaced_near_turn_limit(self):
        _,_,c=self.setup_case()
        proposal={'type':'SAY','target':'meddb:withdrawal_sx','content':'약을 안 드실 때는 어떤가요?'}
        action,_=c.choose(proposal,14,12)
        self.assertEqual(action['target'],'meddb:withdrawal_sx')

    def test_safety_statement_with_target_is_never_rewritten_as_question(self):
        _,_,c=self.setup_case()
        proposal={'type':'SAY','target':'meddb:onset','content':'지금 즉시 도움을 요청하세요.','communication':['safety_net']}
        self.assertEqual(c.choose(proposal,45,12),(proposal,None))

    def setup_case(self, opening='잠을 잘 못 자요.'):
        advisor=ClinicalAdvisor(prepare()['clinical_graph'],opening)
        state=PatientState({'opening':opening},{c['id']:c for c in advisor.concepts()})
        return advisor,state,CoveragePlanner(advisor,state)

    def test_done_is_replaced_with_unasked_core_observation(self):
        _,s,c=self.setup_case()
        action,event=c.choose({'type':'DONE'},45,12)
        self.assertEqual(action['target'],'meddb:onset')
        self.assertEqual(event['reason'],'unasked_core_observation')
        self.assertEqual(len(s.evidence),0)

    def test_attempt_unknown_and_resolved_are_different(self):
        _,s,c=self.setup_case();a=c.actions()[0]
        s.add_response('SAY',a['content'],{'content':'모르겠어요'},a['target'])
        self.assertEqual(c.status(a),'attempted_unresolved')
        next_action,_=c.choose({'type':'DONE'},45,12)
        self.assertNotEqual(next_action['target'],a['target'])
        s.facts.append({'concept_id':a['target'],'assertion':'unknown'})
        self.assertEqual(c.status(a),'attempted_unresolved')
        s.facts.append({'concept_id':a['target'],'assertion':'present'})
        self.assertEqual(c.status(a),'resolved_model_extracted')
        s.facts.append({'concept_id':a['target'],'assertion':'absent'})
        self.assertEqual(c.status(a),'conflicting')

    def test_urgent_bypass_needs_real_source_ids_and_reason(self):
        _,_,c=self.setup_case()
        p={'type':'DONE','urgent_exit':True,'urgency_evidence_ids':['made-up'],'urgent_reason':'즉시 평가'}
        self.assertIsNotNone(c.choose(p,45,12)[1])
        p['urgency_evidence_ids']=['initial']
        self.assertIsNone(c.choose(p,45,12)[1])
        p['urgent_reason']=''
        self.assertIsNotNone(c.choose(p,45,12)[1])

    def test_immediate_safety_statement_is_not_overridden(self):
        _,_,c=self.setup_case()
        p={'type':'SAY','content':'지금 즉시 도움을 요청하세요.','communication':['safety_net']}
        self.assertEqual(c.choose(p,15,12),(p,None))

    def test_premature_plan_is_redirected_but_answer_is_allowed(self):
        _,_,c=self.setup_case()
        p={'type':'SAY','content':'계획을 설명드리겠습니다.','communication':['plan']}
        self.assertIsNotNone(c.choose(p,45,12)[1])
        p['communication']=['answer']
        self.assertIsNone(c.choose(p,45,12)[1])

    def test_initial_mapping_requires_exact_opening_quote(self):
        _,_,c=self.setup_case('세 달째 잠을 잘 못 자요.')
        c.accept_initial([{'target':'meddb:onset','quote':'일 년째'}, {'target':[],'quote':'세 달째'}])
        self.assertEqual(c.status(c.actions()[0]),'unasked')
        c.accept_initial([{'target':'meddb:onset','quote':'세 달째'}])
        self.assertEqual(c.status(c.actions()[0]),'initial_model_mapped')

    def test_exam_result_is_collected_without_asserting_all_signs_normal(self):
        _,s,c=self.setup_case()
        action=next(a for a in c.actions() if a['type']=='EXAM')
        s.add_response('EXAM',action['content'],{'result':'평가 결과'},action['target'])
        self.assertEqual(c.status(action),'exam_result_obtained')
        self.assertFalse(s.facts)

    def test_child_age_and_unknown_complaint_constraints_remain(self):
        _,_,c=self.setup_case('여섯 살 남자아이. 키가 작아요.')
        self.assertFalse(any(a['target']=='meddb:ex_tanner' for a in c.actions()))
        _,_,c=self.setup_case('새로운 알 수 없는 증상입니다.')
        self.assertEqual(c.actions(),[])
        self.assertIsNone(c.choose({'type':'DONE'},45,12)[1])

    def test_target_can_be_linked_outside_first_eight_advisor_actions(self):
        _,_,c=self.setup_case()
        a=next(a for a in c.actions() if a['target']=='meddb:ex_mental')
        self.assertEqual(c.target_for('EXAM',a['content']),a['target'])

    def test_invalid_proposal_still_reaches_existing_validator(self):
        _,_,c=self.setup_case()
        self.assertEqual(c.choose([],45,12),([],None))

    def test_runtime_executes_core_question_instead_of_early_done(self):
        client=ScriptClient([{'next_action':{'type':'DONE'}},{'diagnosis':'평가 중'}],['세 달 전부터요'])
        consult(client,prepare(),Config(max_turns=1,structured_closing=False))
        self.assertEqual(50-client.turns,1)
        self.assertIn('세 달 전부터요',client.submitted['note']['S']['hpi'])


class EvidenceScopeTests(unittest.TestCase):
    def state(self):
        a=ClinicalAdvisor(prepare()['clinical_graph'],'잠을 잘 못 자요.')
        return PatientState({}, {c['id']:c for c in a.concepts()})

    def fact(self,concept,quote,assertion='absent'):
        return {'concept_id':concept,'evidence_id':'e1','quote':quote,'assertion':assertion}

    def test_awake_reply_does_not_establish_absence_of_another_symptom(self):
        s=self.state();s.add_response('SAY','깨어 있고 숨은 편한가요?',{'content':'네, 지금 깨어 있어요.'})
        accepted,rejected=s.accept_facts([self.fact('meddb:daytime_sedation','지금 깨어 있어요')])
        self.assertFalse(accepted);self.assertTrue(rejected)

    def test_non_worsening_is_not_absolute_absence(self):
        s=self.state();s.add_response('SAY','평소보다 심하게 졸리신가요?',{'content':'평소보다 심하진 않아요.'})
        self.assertFalse(s.accept_facts([self.fact('meddb:daytime_sedation','심하진 않아요')])[0])

    def test_explicit_unknown_cannot_be_present_or_absent(self):
        s=self.state();s.add_response('SAY','수면제를 드시나요?',{'content':'모르겠어요'})
        for assertion in ('present','absent'):
            self.assertFalse(s.accept_facts([self.fact('meddb:hypnotic_use','모르겠어요',assertion)])[0])
        self.assertTrue(s.accept_facts([self.fact('meddb:hypnotic_use','모르겠어요','unknown')])[0])

    def test_negative_from_actual_targeted_exam_does_not_expand_to_other_signs(self):
        s=self.state();s.add_response('EXAM','갑상선을 촉진하겠습니다.',{'result':'정상'},'meddb:ex_thyroid')
        self.assertTrue(s.accept_facts([self.fact('meddb:goiter','정상')])[0])
        self.assertFalse(s.accept_facts([self.fact('meddb:sedation_sign','정상')])[0])

    def test_explicit_negative_still_accepted(self):
        s=self.state();s.add_response('SAY','낮에 졸리시나요?',{'content':'아니요, 없어요.'})
        self.assertTrue(s.accept_facts([self.fact('meddb:daytime_sedation','없어요')])[0])

    def test_exposure_only_cannot_be_rendered_as_confirmed_syndrome(self):
        value=normalize_assessment({'diagnosis':'평가할 병태','certainty':'confirmed','diagnostic_basis':'exposure_risk_only'})
        self.assertEqual(value['certainty'],'suspected')
        self.assertIn('의심',value['diagnosis'])

    def test_education_statements_leave_hpi_but_new_patient_information_survives(self):
        s=self.state()
        s.add_response('SAY','검사 후 계획을 정하겠습니다.',{'content':'낮에도 증상이 있어요.'},communication=['plan'])
        note,_=make_record(s,{'diagnosis':'평가 중'})
        self.assertNotIn('검사 후 계획을 정하겠습니다.',note['S']['hpi'])
        self.assertIn('낮에도 증상이 있어요.',note['S']['hpi'])
        self.assertIn('검사 후 계획을 정하겠습니다.',note['P']['education'])


if __name__=='__main__':unittest.main()
