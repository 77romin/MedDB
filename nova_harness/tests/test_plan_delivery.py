import unittest
from copy import deepcopy
from nova_agent.plan_delivery import PlanDelivery


class PlanDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.note={'P':{'education':'숨이 차면 즉시 응급실 방문하도록 설명함.','follow_up':'1주 후 재진'}}
        self.row={'source_field':'education','source_quote':self.note['P']['education'],
                  'condition':'숨이 차면','action':'즉시 응급실 방문','timing':'즉시',
                  'priority':'critical','applicability':'conditional',
                  'messages':['숨이 차면 즉시 응급실 방문하세요.']}
        self.d=PlanDelivery();self.d.compile(self.note,{'obligations':[self.row]},1)
    def speech(self,text=None,count=1,index=0):
        return {'index':index,'record_count':count,'content':text or self.row['messages'][0]}
    def test_specific_warning_not_generic_substitute(self):
        a=self.d.audit(self.note,[self.speech('더 힘들면 진료받으세요.')])
        self.assertEqual(a['groups'][0]['state'],'unresolved')
    def test_acknowledged_exact_warning(self):
        self.assertEqual(self.d.audit(self.note,[self.speech()])['groups'][0]['state'],'sent_success')
    def test_old_record_or_later_record_not_credited(self):
        for n in (0,2):self.assertEqual(self.d.audit(self.note,[self.speech(count=n)])['groups'][0]['state'],'unresolved')
    def test_plan_change_invalidates_same_text(self):
        n=deepcopy(self.note);n['P']['follow_up']='내일 재진'
        self.assertTrue(self.d.audit(n,[self.speech()])['plan_changed'])
        self.assertEqual(self.d.audit(n,[self.speech()])['groups'][0]['state'],'unresolved')
    def test_raw_completion_not_actual(self):
        out=self.d.render(self.note,[])
        actual=out['P']['education'].split('실제 전달 기록',1)[1]
        self.assertNotIn('설명함',actual);self.assertIn('확인된 전달 없음',actual)
    def test_upstream_append_does_not_change_plan(self):
        n=deepcopy(self.note);n['P']['education']+='\n환자에게 설명함: 임의 문구\n이해 확인 답변: 네'
        self.assertFalse(self.d.audit(n,[self.speech()])['plan_changed'])
    def test_whole_group_budget_and_order(self):
        self.row['messages']=['숨이 차면 즉시 응급실 방문하세요.','증상이 있으면 바로 알려 주세요.']
        self.d.compile(self.note,{'obligations':[self.row]},1)
        self.assertEqual(self.d.schedule(1),[])
        self.assertEqual(len(self.d.schedule(2)),2)
        wrong=[self.speech(self.row['messages'][1],index=0),self.speech(index=1)]
        self.assertEqual(self.d.audit(self.note,wrong)['groups'][0]['state'],'unresolved')
    def test_lost_urgency_rejected(self):
        self.row['messages']=['숨이 차면 병원에 방문하세요.']
        self.assertEqual(self.d.compile(self.note,{'obligations':[self.row]},1),[])
    def test_overlength_rejected_not_clipped(self):
        self.row['messages']=['숨이 차면 즉시 응급실 방문하세요. 반드시 지금 바로 가까운 응급실로 방문해 주세요.']
        self.assertEqual(self.d.compile(self.note,{'obligations':[self.row]},1),[])
    def test_partial_delivery_not_complete(self):
        self.row['messages']=['숨이 차면 즉시 응급실 방문하세요.','증상이 있으면 바로 알려 주세요.']
        self.d.compile(self.note,{'obligations':[self.row]},1)
        self.assertEqual(self.d.audit(self.note,[self.speech()])['groups'][0]['state'],'unresolved')

if __name__=='__main__':unittest.main()

class ClosingIntegrationTests(unittest.TestCase):
    def test_one_compile_no_legacy_generic_rewrite_and_acknowledged_submission(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/meddb'))
        from examples import hybrid_comm as C
        from nova_agent import plan_delivery
        from nova_agent.safety_trace import SafetyTimeline,TimelineClient
        note={'P':{'education':'숨이 차면 즉시 응급실 방문하도록 설명함.','follow_up':'1주 후 재진'}}
        row={'source_field':'education','source_quote':note['P']['education'],
             'condition':'숨이 차면','action':'즉시 응급실 방문','timing':'즉시',
             'priority':'critical','applicability':'conditional',
             'messages':['숨이 차면 즉시 응급실 방문하세요.']}
        class Raw:
            calls=0
            def session(self):return {'turns_remaining':8,'deadline_at':'2099-01-01T00:00:00Z'}
            def chat(self,*a,**kw):
                import json
                self.calls+=1
                return {'choices':[{'message':{'content':json.dumps({'obligations':[row]},ensure_ascii=False)}}]}
            def say(self,text,**kw):return {'reply':'네'}
            def diagnose(self,*,note,diagnosis,**kw):self.final=note;return {}
        raw=Raw();timeline=SafetyTimeline();timeline.records.append({'note':note})
        original=plan_delivery.install(timeline)
        try:
            client=plan_delivery.Client(TimelineClient(raw,timeline),timeline)
            messages=C._closing_sentences(client,None,note,'진단','',True)
            self.assertEqual(messages,row['messages']);self.assertEqual(raw.calls,1)
            client.say(messages[0]);client.diagnose(note=note,diagnosis='진단')
            performed=raw.final['P']['education'].split('실제 전달 기록',1)[1]
            self.assertIn(messages[0],performed);self.assertNotIn('설명함',performed)
            self.assertIn('1/1',performed)
        finally:plan_delivery.restore(original)
