import unittest

from nova_agent.goals import DecisionGoals
from nova_agent.state import PatientState
from nova_agent.runtime import consult, prepare
from test_harness import ScriptClient, Config


def goal(**kwargs):
    return dict({'id':'exposure', 'need':'실제 노출 범위', 'scope':'환자 오늘',
                 'status':'open', 'priority':'safety', 'reason':'일부 시간만 확인', 'evidence':[]}, **kwargs)


class DecisionGoalTests(unittest.TestCase):
    def test_asking_or_planning_without_patient_evidence_cannot_resolve(self):
        s=PatientState({}, {});s.add_response('SAY','추가 복용은요?',{'content':'모르겠어요'})
        g=DecisionGoals(s)
        for refs in ([], [{'id':'e1','quote':'복용 안 함'}], [{'id':'e1','quote':'모르겠어요'}]):
            accepted,rejected=g.update([goal(status='resolved',evidence=refs)])
            self.assertFalse(accepted);self.assertTrue(rejected)

    def test_time_scopes_cannot_be_silently_broadened(self):
        s=PatientState({}, {});s.add_response('SAY','오늘 병용은요?',{'content':'오늘은 안 먹었어요.'})
        g=DecisionGoals(s)
        self.assertTrue(g.update([goal(status='resolved',evidence=[{'id':'e1','quote':'오늘은 안 먹었어요.'}])])[0])
        self.assertFalse(g.update([goal(scope='환자 평소 간헐적 병용',status='resolved',
                                       evidence=[{'id':'e1','quote':'오늘은 안 먹었어요.'}])])[0])
        self.assertEqual(g.snapshot()['goals'][0]['scope'],'환자 오늘')
        self.assertTrue(g.update([goal(id='usual_exposure',scope='환자 평소 간헐적 병용')])[0])

    def test_partial_answer_keeps_gap_and_source_without_asserting_normal(self):
        s=PatientState({}, {});s.add_response('EXAM','호흡 상태를 봅니다.',{'result':'보조호흡근 사용(-)'})
        g=DecisionGoals(s)
        accepted,_=g.update([goal(id='respiration',status='partial',scope='현재 호흡 상태',
                                reason='관찰 소견만 반환, 수치 미확인',evidence=[{'id':'e1','quote':'보조호흡근 사용(-)'}])])
        self.assertEqual(accepted[0]['status'],'partial')
        self.assertEqual(s.snapshot()['decision_goals'],g.snapshot()['goals'])
        self.assertNotIn('산소포화도 정상',str(s.snapshot()))

    def test_review_adds_one_targeted_followup_then_submits(self):
        steps=[{'next_action':{'type':'SAY','content':f'{i}번은 어떤가요?','communication':['plan']}} for i in range(3)]
        audit={'ready':False,'urgent_exit':False,'missing':['실제 수치'],
               'next_action':{'type':'SAY','content':'기록된 수치를 알려주시겠어요?'}}
        client=ScriptClient(steps+[{'next_action':{'type':'DONE'}},audit,{'next_action':{'type':'DONE'}},
                                   {'diagnosis':'평가 중'}],['기록 있어요']*3+['그 수치는 몰라요'])
        result=consult(client,prepare(),Config(max_turns=20,decision_review=True,closure_review_limit=1))
        self.assertEqual(result['status'],'completed')
        self.assertEqual(sum(method=='say' for method,_ in client.requests),4)

    def test_source_cited_urgent_done_does_not_wait_for_review(self):
        steps=[{'next_action':{'type':'SAY','content':f'{i}번은 어떤가요?','communication':['safety_net']}} for i in range(3)]
        done={'next_action':{'type':'DONE','urgent_exit':True,'urgency_evidence_ids':['e3'],
                             'urgent_reason':'즉시 대응 지연 방지'}}
        client=ScriptClient(steps+[done,{'diagnosis':'추가 평가 필요'}],['상태 변화']*3)
        consult(client,prepare(),Config(max_turns=20,decision_review=True))
        self.assertEqual(sum(method=='chat' for method,_ in client.requests),5)

    def test_completed_goals_do_not_block_new_active_information(self):
        s=PatientState({'opening':'기존 응답'},{});g=DecisionGoals(s)
        for i in range(8):
            a,r=g.update([goal(id='closed_'+str(i),status='resolved',evidence=[{'id':'initial','quote':'기존 응답'}])])
            self.assertFalse(r)
        a,r=g.update([goal(id='new_safety_need')])
        self.assertTrue(a);self.assertFalse(r)
        self.assertEqual(len(s.decision_goals),9)
        self.assertEqual(g.snapshot()['active_count'],1)
        self.assertEqual(g.snapshot()['archived_count'],4)
        self.assertEqual(len(g.snapshot()['goals']),5)
        self.assertEqual(len(s.prompt_snapshot()['decision_goals']),5)
        self.assertEqual(len(s.snapshot()['decision_goals']),9)

    def test_active_goal_limit_does_not_allow_reactivation_to_bypass_bound(self):
        s=PatientState({'opening':'응답'},{});g=DecisionGoals(s)
        g.update([goal(id='closed',status='resolved',evidence=[{'id':'initial','quote':'응답'}])])
        for i in range(8):self.assertTrue(g.update([goal(id='active_'+str(i))])[0])
        self.assertFalse(g.update([goal(id='closed')])[0])
        self.assertFalse(g.update([goal(id='new')])[0])
        self.assertEqual(g.snapshot()['active_count'],8)


if __name__=='__main__':unittest.main()
