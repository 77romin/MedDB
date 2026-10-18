import unittest
from nova_agent.decision_axes import decision_axes
from nova_agent.state import PatientState


class DecisionAxesTest(unittest.TestCase):
    def test_doctor_question_does_not_establish_exposure(self):
        s=PatientState({'opening':'속이 아파요'}, {})
        s.add_response('SAY','수면제를 먹었나요?',{'content':'모르겠어요'})
        self.assertIsNone(decision_axes(s))

    def test_actual_medication_reply_activates_scopes_without_resolving(self):
        s=PatientState({'opening':'어지러워요'}, {})
        s.add_response('SAY','복용약은요?',{'content':'어젯밤 수면제를 두 알 먹었어요'})
        axes=decision_axes(s)['axes']
        self.assertEqual(axes[0]['type'],'medication_exposure')
        self.assertIn('24시간',str(axes))
        self.assertFalse(s.facts)
        self.assertFalse(s.decision_goals)
        self.assertNotIn('resolved',str(axes))

    def test_education_reply_cannot_activate_a_new_diagnosis_scope(self):
        s=PatientState({'opening':'걱정돼요'}, {})
        s.add_response('SAY','복용을 확인하겠습니다.',{'content':'수면제가 무슨 뜻인가요?'},communication=['plan'])
        self.assertIsNone(decision_axes(s))

    def test_thyroid_hypothesis_is_not_a_confirmed_condition_or_pregnancy(self):
        s=PatientState({'opening':'두근거려요'}, {})
        c={'age':28,'sex':'F','hypotheses':[{'label':'갑상선기능항진증'}]}
        result=decision_axes(s,c)
        self.assertIn('임신',str(result));self.assertEqual(len(result['axes']),1)
        self.assertFalse(s.facts)
        c['sex']='M';self.assertNotIn('임신 가능성/계획',str(decision_axes(s,c)))
        c.update(sex='F',age=70);self.assertNotIn('임신 가능성/계획',str(decision_axes(s,c)))

    def test_growth_family_temporal_distinctions_do_not_invent_family_facts(self):
        s=PatientState({'opening':'아이가 키가 작아요'}, {})
        self.assertEqual(decision_axes(s,{'age':9})['axes'][0]['type'],'growth_trajectory')
        self.assertFalse(s.facts)
        self.assertIsNone(decision_axes(s,{'age':40}))

    def test_growth_complaint_handles_nonadjacent_opening_wording(self):
        s=PatientState({'opening':'키가 또래에 비해 많이 작은 것 같아요'}, {})
        self.assertEqual(decision_axes(s,{'age':6,'complaint':'short_stature'})['axes'][0]['type'],'growth_trajectory')
