"""Observed failure shapes and counterexamples; no public case answers."""
import json
from pathlib import Path
import unittest
import test_coverage as coverage_fixture
from nova_agent.state import PatientState
from nova_agent.closing import statement_parts, statement_queue


class DecisionRegressions(unittest.TestCase):
    def setup(self):
        return coverage_fixture.CoverageTests().setup_case()

    def test_out_of_graph_risk_questions_survive_even_near_closing(self):
        for question in ['두근거릴 때 실신한 적 있나요?','졸려서 넘어지거나 다친 적 있나요?',
                         '증상이 갑자기 심해졌나요?','가족 중 비슷한 병이 있었나요?']:
            for remaining in [13,16,45]:
                with self.subTest(question=question,remaining=remaining):
                    _,_,c=self.setup();p={'type':'SAY','content':question,'communication':[]}
                    action,event=c.choose(p,remaining,12)
                    self.assertEqual(action['content'],question);self.assertEqual(action['type'],'SAY')
                    self.assertIsNone(event)

    def test_same_target_paraphrase_cannot_repeat_exam_without_new_evidence(self):
        _,s,c=self.setup();s.add_response('EXAM','의식·지남력 평가를 하겠습니다.',{'result':'소견','turn':1},'meddb:ex_mental')
        p={'type':'EXAM','target':'meddb:ex_mental','content':'정신 상태를 살펴보겠습니다.'}
        with self.assertRaises(ValueError):c.choose(p,30,12)
        p.update(reassessment_reason='상태 변화',reassessment_evidence_ids=['e1'])
        with self.assertRaises(ValueError):c.choose(p,30,12)
        s.add_response('SAY','상태가 달라졌나요?',{'content':'방금 더 나빠졌어요','turn':2})
        p['reassessment_evidence_ids']=['e2']
        self.assertEqual(c.choose(p,30,12),(p,None))

    def test_mistaken_history_target_cannot_rewrite_risk_question(self):
        _,_,c=self.setup()
        p={'type':'SAY','target':'meddb:family','content':'최근 넘어지거나 다친 적 있나요?'}
        self.assertEqual(c.choose(p,13,12),(p,None))

    def test_different_exam_is_not_blocked(self):
        _,s,c=self.setup();s.add_response('EXAM','평가',{'result':'소견'},'meddb:ex_mental')
        p={'type':'EXAM','target':'meddb:ex_tremor','content':'자세성 떨림을 확인하겠습니다.'}
        self.assertEqual(c.choose(p,30,12)[0]['target'],p['target'])

    def test_structured_measurements_keep_exact_values_units_and_time(self):
        s=PatientState({}, {'dose':{'field':'pmh'}})
        s.add_response('SAY','마지막 복용은요?',{'content':'오늘 새벽에 2알, 한 알은 10밀리그램이에요.'})
        f={'concept_id':'dose','assertion':'present','evidence_id':'e1','quote':'오늘 새벽에 2알',
           'attribute':'dose_count','value':'2','unit':'알','time_anchor':'오늘 새벽'}
        a,r=s.accept_facts([f]);self.assertFalse(r);self.assertEqual(a[0]['value'],'2')
        for change in [{'value':'20'},{'unit':'mg'},{'time_anchor':'어젯밤'}]:
            with self.subTest(change=change):self.assertFalse(s.accept_facts([{**f,**change}])[0])

    def test_value_cannot_be_borrowed_from_question_or_outside_partial_quote(self):
        s=PatientState({}, {'dose':{'field':'pmh'}})
        s.add_response('SAY','10mg인가요?',{'content':'모르겠어요'})
        self.assertFalse(s.accept_facts([{'concept_id':'dose','assertion':'unknown','evidence_id':'e1',
                         'quote':'모르겠어요','attribute':'strength','value':'10'}])[0])

    def test_model_authored_counterexamples_after_manual_inspection(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/synthetic_extraction.json').read_text())
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                s=PatientState({}, {'test:observation':{'field':'pmh'}})
                s.add_response('SAY',case['question'],{'content':case['response']})
                self.assertEqual(bool(s.accept_facts([case['proposed_fact']])[0]),case['expected_accept'])

    def test_family_subject_with_explicit_family_mapping_still_works(self):
        s=PatientState({}, {'x':{'field':'fh'}})
        s.add_response('SAY','가족력은요?',{'content':'어머니는 고혈압이 있어요.'})
        self.assertTrue(s.accept_facts([{'concept_id':'x','evidence_id':'e1','quote':'어머니는 고혈압이 있어요.',
                                      'assertion':'present','subject':'family'}])[0])

    def test_malformed_attribute_is_rejected_without_crashing(self):
        s=PatientState({}, {'dose':{'field':'pmh'}})
        s.add_response('SAY','질문',{'content':'두 알'})
        fact={'concept_id':'dose','assertion':'present','evidence_id':'e1','quote':'두 알','value':'두','attribute':[]}
        self.assertFalse(s.accept_facts([fact])[0])

    def test_context_scoping_retains_all_raw_evidence_and_facts(self):
        s=PatientState({'opening':'시작'}, {str(i):{} for i in range(325)})
        s.add_response('SAY','질문',{'content':'원문 답변'})
        snap=s.prompt_snapshot(['1','2']);self.assertEqual(snap['unconfirmed_slots'],['1','2'])
        self.assertEqual(snap['evidence'][0]['response'],'원문 답변')
        self.assertEqual(len(s.snapshot()['unconfirmed_slots']),325)
        self.assertNotIn('unconfirmed_slots',s.prompt_snapshot())
        s.compact_context=False;self.assertEqual(len(s.prompt_snapshot()['unconfirmed_slots']),325)

    def test_essential_plan_is_sent_before_repeated_assessment(self):
        m={'safety_net':['악화 시 진료받으세요.','즉시 도움을 요청하세요.'],
           'assessment':['추가 확인이 필요합니다.','검사 전에는 확정할 수 없어요.'],
           'plan':['오늘 진료를 받으세요.','약 포장을 가져오세요.'],
           'follow_up':['내일 결과를 확인하세요.'],'concern':['함께 확인하겠습니다.'],
           'essential':[{'tag':'plan','index':1}]}
        parsed={tag:statement_parts(m[tag]) for tag in ('safety_net','assessment','plan','follow_up','concern')}
        q=statement_queue(m,parsed)
        self.assertLess(q.index(('plan',m['plan'][1])),q.index(('assessment',m['assessment'][1])))
        self.assertEqual(len(q),len(set(q)))
        m['essential']=[{'tag':[],'index':0},{'tag':'plan','index':False}]
        # Bad metadata is ignored, rather than breaking record submission.
        self.assertEqual(len(statement_queue(m,parsed)),len(q))


if __name__=='__main__':unittest.main()
