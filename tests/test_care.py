import unittest
from meddb import MedDB
from meddb.coverage import CareCoverage
from examples.hybrid_agent import Tracker, write_record


class CareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.db = MedDB.open()

    def test_child_growth_does_not_request_puberty_exam(self):
        tracker = Tracker(self.db, 'short_stature', 6, 'M', '', {})
        planner = CareCoverage(self.db, 'short_stature', 6, 'M')
        targets = [a['target'] for a in planner.needed(tracker)]
        self.assertNotIn('ex_tanner', targets)
        self.assertIn('parent_father', targets)
        self.assertIn('parent_mother', targets)
        self.assertFalse(planner.allow_action(tracker,'EXAM','사춘기 성숙도 평가','ex_tanner'))

    def test_chronic_history_does_not_repeat_generic_pmh_and_child_is_subject(self):
        tracker=Tracker(self.db,'short_stature',6,'M','',{})
        planner=CareCoverage(self.db,'short_stature',6,'M')
        planner.observe('chronic_illness','오래 앓고 있는 병이 있나요?','아이는 없어요',1)
        actions=planner.needed(tracker)
        self.assertNotIn('pmh',[a['target'] for a in actions])
        meds=next(a for a in actions if a['target']=='meds')
        self.assertTrue(meds['text'].startswith('아이가'))

    def test_pregnancy_only_when_applicable_and_no_unasked_fact(self):
        for sex,age,expected in [('F',32,True),('M',32,False),('F',70,False)]:
            tracker=Tracker(self.db,'weight_loss',age,sex,'',{})
            planner=CareCoverage(self.db,'weight_loss',age,sex)
            self.assertEqual('pregnancy' in [a['target'] for a in planner.needed(tracker)],expected)
            note=self.db.empty_note();planner.append_record(note)
            self.assertTrue(all(not text for text in note['S'].values()))

    def test_unknown_complaint_still_collects_basic_history(self):
        tracker=Tracker(self.db,None,40,'M','',{})
        planner=CareCoverage(self.db,None,40,'M')
        targets=[a['target'] for a in planner.needed(tracker)]
        self.assertIn('onset',targets)
        self.assertIn('meds',targets)
        self.assertIn('allergy',targets)

    def test_medication_details_follow_actual_use_and_limit_is_respected(self):
        tracker=Tracker(self.db,'insomnia',62,'F','',{})
        planner=CareCoverage(self.db,'insomnia',62,'F')
        self.assertNotIn('med_duration',[a['target'] for a in planner.needed(tracker)])
        tracker.mark('hypnotic_use','+',1,'수면제를 먹어요')
        self.assertIn('med_duration',[a['target'] for a in planner.needed(tracker)])
        for action in planner.needed(tracker):self.assertLessEqual(len(action['text']),30)

    def test_planner_exhausts_without_repeating_completed_actions(self):
        for complaint,age,sex in [('insomnia',62,'F'),('short_stature',6,'M'),('weight_loss',32,'F'),('chest_pain',55,'M')]:
            tracker=Tracker(self.db,complaint,age,sex,'',{})
            planner=CareCoverage(self.db,complaint,age,sex);sent=[]
            for turn in range(1,40):
                actions=planner.needed(tracker)
                if not actions:break
                action=actions[0];sent.append(action['text'])
                planner.observe(action['target'],action['text'],'잘 모르겠어요',turn)
                if action['type']=='EXAM':tracker.exams_done.add(action['target'])
            self.assertFalse(planner.needed(tracker))
            self.assertEqual(len(sent),len(set(sent)))
            self.assertLessEqual(len(sent),36)

    def test_completed_extra_answers_are_preserved_verbatim(self):
        planner=CareCoverage(self.db,'insomnia',62,'F')
        planner.observe('med_schedule','그 약을 하루에 얼마나 드세요?','약 이름은 모르고 반 알 먹어요',7)
        note=self.db.empty_note();planner.append_record(note)
        self.assertIn('약 이름은 모르고 반 알 먹어요',note['S']['pmh'])
        self.assertNotIn('med_duration',note['S']['pmh'])

    def test_personalized_plan_survives_record_normalization(self):
        from test_clinical_safety import Client
        tracker=Tracker(self.db,'chest_pain',58,'M','',{})
        record={'S':{'cc':'흉통'},'A':{'evidence':'#1. 공황발작\n- 환자와 확인한 근거','differential':'별도로 평가한 감별 근거'},
                'P':{'follow_up':'검사 결과 확인 후 재진 일정 조율','tests':'심전도로 위험 원인 평가'},'diagnosis':'공황발작'}
        note,dx=write_record(Client(record),self.db,tracker,'',{},[],contextual_plan=True)
        self.assertEqual(note['P']['follow_up'],record['P']['follow_up'])
        self.assertEqual(note['A']['differential'],record['A']['differential'])

    def test_end_to_end_collects_history_before_accepting_done(self):
        from test_meddb import ScriptedLLM
        from examples.hybrid_care import consult
        client=ScriptedLLM('58세 남자입니다. 가슴이 아파요.',[{'action':'DONE'}],
                           {'S':{'cc':'흉통'},'diagnosis':'공황발작'})
        consult(client,self.db,knowledge_mode='clinical')
        self.assertIsNotNone(client.submitted)
        questions=[text for kind,text in client.log if kind=='SAY']
        self.assertIn(self.db.slots['allergy']['ask'],questions)
        self.assertIn(self.db.slots['meds']['ask'],questions)
        self.assertIn('집에서 어떻게 하실지 말씀해 주시겠어요?',questions)
        self.assertLessEqual(client.turn,50)

    def test_transport_retry_reuses_id_and_nonretryable_error_is_not_retried(self):
        from unittest.mock import patch
        from examples.consult_skeleton import with_retry, NovaError
        ids=[]
        class Failure(NovaError):
            def __init__(self,status):
                self.code='INVALID_API_RESPONSE';self.status=status
        def call(*,request_id=None):
            ids.append(request_id)
            if len(ids)<3:raise Failure(429)
            return 'ok'
        with patch('examples.consult_skeleton.time.sleep'):
            self.assertEqual(with_retry(call),'ok')
        self.assertEqual(len(set(ids)),1)
        self.assertIsNotNone(ids[0])
        def forbidden(*,request_id=None):raise Failure(403)
        with self.assertRaises(Failure),patch('examples.consult_skeleton.time.sleep') as sleep:
            with_retry(forbidden)
        sleep.assert_not_called()

    def test_pending_keeps_id_but_invalid_generated_reply_gets_new_id(self):
        from unittest.mock import patch
        from examples.consult_skeleton import with_retry, NovaError
        class Failure(NovaError):
            def __init__(self,code):self.code=code;self.status=409
        for code,expected_same in [('REQUEST_PENDING',True),('PATIENT_RESPONSE_INVALID',False)]:
            ids=[]
            def call(*,request_id=None):
                ids.append(request_id)
                if len(ids)==1:raise Failure(code)
                return 'ok'
            with patch('examples.consult_skeleton.time.sleep'):
                self.assertEqual(with_retry(call),'ok')
            self.assertEqual(ids[0]==ids[1],expected_same)


if __name__=='__main__':unittest.main()
