import unittest
import json
from pathlib import Path

from nova_agent.closing import close_consultation, short_statement, statement_parts
from nova_agent.records import make_record
from nova_agent.protocol import Gateway
from nova_agent.config import Config
from nova_agent.runtime import prepare
from nova_agent.state import PatientState
from nova_agent.telemetry import Trace
from test_harness import ScriptClient


class ClosingTests(unittest.TestCase):
    def test_teach_back_does_not_assume_patient_is_at_home(self):
        plan={'diagnosis':'평가 중','plan':{}}
        state=self.state();client=ScriptClient([plan,{},plan],['걱정돼요','알겠습니다'])
        close_consultation(Gateway(client),state,plan,8,Trace())
        self.assertTrue(any('어떻게 하실지' in e.question for e in state.evidence))
        self.assertFalse(any('집에서' in e.question for e in state.evidence))

    def state(self):
        return PatientState({'opening':'환자 시작 정보'}, {c['id']:c for c in prepare()['concepts']})

    def test_proxy_failure_on_concern_question_recovers_before_explanation(self):
        from nova_sdk import NovaError
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'plan':['검사 후 계획을 정하겠습니다.']}
        client=ScriptClient([plan,messages,plan],
                            [NovaError('INVALID_API_RESPONSE',502),'걱정돼요','네','알겠습니다'])
        state=self.state()
        close_consultation(Gateway(client,sleeper=lambda _:None),state,plan,8,Trace())
        say_ids=[rid for method,rid in client.requests if method=='say']
        self.assertEqual(say_ids[0],say_ids[1])
        self.assertEqual(50-client.turns,3)
        self.assertTrue(any(e.question==messages['plan'][0] for e in state.delivered_explanations()))

    def test_complete_sentence_selection_does_not_truncate(self):
        self.assertEqual(short_statement('검사로 확인할게요. 결과를 확인하고 계획을 함께 정하겠습니다.'),'검사로 확인할게요.')
        self.assertIsNone(short_statement('가'*31))
        self.assertIsNone(short_statement('무슨 약인가요?'))

    def test_legacy_adapter_preserves_two_short_sentences_when_whole_value_fits(self):
        text='검사로 확인해요. 결과를 기다려요.'
        self.assertLessEqual(len(text),30)
        self.assertEqual(short_statement(text),text)

    def test_connecting_clause_is_not_a_complete_statement(self):
        parts,bad=statement_parts(['원인이 의심되지만','검사로 확인해야 합니다.'])
        self.assertEqual(parts,['검사로 확인해야 합니다.'])
        self.assertEqual(bad,['원인이 의심되지만'])

    def test_real_overlong_closing_has_complete_short_sentences(self):
        messages=json.loads((Path(__file__).parent/'fixtures/overlong_closing.json').read_text())
        self.assertTrue(all(len(x)>30 for x in messages.values()))
        # Every source paragraph contains a standalone sentence that fits the actual protocol.
        for text in messages.values():
            sentence=short_statement(text)
            self.assertIsNotNone(sentence)
            self.assertIn(sentence,text)
            self.assertLessEqual(len(sentence),30)

    def test_failed_long_output_can_be_repaired_and_sent(self):
        plan={'diagnosis':'평가 중','plan':{'education':'교육 계획'}}
        long={'assessment':'가'*40,'plan':'나'*40}
        short={'assessment':'원인을 더 확인해야 해요.','plan':'검사 후 계획을 정하겠습니다.'}
        client=ScriptClient([plan,long,short,plan],['잠이 걱정돼요','네','네','검사받을게요'])
        state=self.state()
        revised,left=close_consultation(Gateway(client,Config()),state,plan,8,Trace())
        self.assertEqual(50-client.turns,4)
        note,_=make_record(state,revised)
        self.assertIn(short['assessment'],note['P']['education'])
        self.assertNotIn('가'*40,note['P']['education'])
        self.assertEqual(left,4)

    def test_unavailable_generation_does_not_claim_unsent_education(self):
        from nova_sdk import NovaError
        plan={'diagnosis':'평가 중','plan':{}}
        client=ScriptClient([plan,NovaError('MODEL_CALL_LIMIT'),plan],['모르겠어요','네'])
        revised,_=close_consultation(Gateway(client),self.state(),plan,8,Trace())
        self.assertNotIn('실제 SAY 설명',revised['plan'].get('education',''))

    def test_all_complete_parts_are_preserved_without_character_slicing(self):
        text='검사로 확인할게요. 결과 후 계획을 정하겠습니다.'
        parts,bad=statement_parts(text)
        self.assertEqual(parts,['검사로 확인할게요.','결과 후 계획을 정하겠습니다.'])
        self.assertFalse(bad)
        parts,bad=statement_parts(['가'*31,'안내드리겠습니다.'])
        self.assertEqual(parts,['안내드리겠습니다.'])
        self.assertEqual(bad,['가'*31])

    def test_two_sentences_for_one_purpose_are_actually_sent(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['원인을 더 확인해야 해요.'],
                  'plan':['검사 후 계획을 정하겠습니다.'],
                  'safety_net':['심한 증상은 즉시 알려주세요.','그때는 응급 평가를 받으세요.']}
        state=self.state()
        client=ScriptClient([plan,messages,plan],['걱정돼요']+['네']*5)
        close_consultation(Gateway(client),state,plan,10,Trace())
        actual=[e.question for e in state.delivered_explanations()]
        self.assertIn(messages['safety_net'][0],actual)
        self.assertIn(messages['safety_net'][1],actual)

    def test_intervening_patient_question_is_answered_before_next_scripted_message(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['원인을 더 확인해야 해요.'],
                  'plan':['검사 후 계획을 정하겠습니다.']}
        answer='검사 결과를 보고 결정하겠습니다.'
        state=self.state()
        client=ScriptClient([plan,messages,{'answer':[answer]},plan],
                            ['걱정돼요','치료할 수 있나요?','네','네','알겠습니다'])
        close_consultation(Gateway(client),state,plan,10,Trace())
        actual=[e.question for e in state.evidence]
        index=actual.index(messages['assessment'][0])
        self.assertEqual(actual[index+1],answer)
        self.assertEqual(state.evidence[index+1].communication,('answer',))

    def test_actual_education_does_not_come_from_model_claims(self):
        state=self.state()
        state.add_response('SAY','검사 후 다시 말씀드릴게요.',{'content':'네','turn':1},communication=['plan'])
        state.add_response('EXAM','관찰',{'result':'시행됨','turn':2},communication=['safety_net'])
        note,_=make_record(state,{'diagnosis':'평가 중','plan':{'education':'추가 상담 계획'}})
        actual,planned=note['P']['education'].split('추가 교육 계획(수행 확인 아님):')
        self.assertIn('검사 후 다시 말씀드릴게요.',actual)
        self.assertNotIn('추가 상담 계획',actual)
        self.assertNotIn('관찰',actual)
        self.assertIn('추가 상담 계획',planned)

    def test_failed_say_and_generated_but_unsent_text_are_not_actual_education(self):
        from nova_sdk import NovaError
        plan={'diagnosis':'평가 중','plan':{'education':'예정된 교육'}}
        messages={'assessment':['설명드릴 내용입니다.']}
        state=self.state()
        client=ScriptClient([plan,messages,plan],['걱정돼요',NovaError('SESSION_CLOSED')])
        revised,left=close_consultation(Gateway(client),state,plan,8,Trace())
        self.assertEqual(left,0)
        self.assertFalse(state.delivered_explanations())
        self.assertEqual(len([r for r in client.requests if r[0]=='chat']),2)
        note,_=make_record(state,revised)
        self.assertNotIn('설명드릴 내용입니다.',note['P']['education'])
        self.assertIn('교육 완료로 간주하지 않음',note['P']['education'])

    def test_teach_back_misunderstanding_gets_one_actual_correction(self):
        plan={'diagnosis':'평가 중','plan':{}}
        revised={**plan,'clarification':['검사 후 계획을 함께 정해요.']}
        state=self.state()
        client=ScriptClient([plan,{'plan':['검사로 확인하겠습니다.']},revised],
                            ['걱정돼요','네','지금 끝난 건가요?','알겠습니다'])
        close_consultation(Gateway(client),state,plan,8,Trace())
        self.assertEqual(state.evidence[-1].question,revised['clarification'][0])
        self.assertIn(state.evidence[-1],state.delivered_explanations())

    def test_turn_budget_reserves_teach_back_and_does_not_send_omitted_messages(self):
        plan={'diagnosis':'평가 중','plan':{}}
        state=self.state()
        client=ScriptClient([plan,plan],['걱정돼요','알겠습니다'])
        revised,left=close_consultation(Gateway(client),state,plan,2,Trace())
        self.assertEqual(left,0)
        self.assertEqual(len(state.evidence),2)
        self.assertFalse(state.delivered_explanations())

    def test_early_done_cannot_spend_all_unused_collection_turns_on_closing(self):
        from nova_agent.runtime import consult
        plan={'diagnosis':'평가 중','plan':{}}
        messages={tag:[f'{i}번 내용을 설명드려요.',f'{i}번 내용을 보완해요.',f'{i}번 안내를 마칩니다.']
                  for i,tag in enumerate(('assessment','plan','follow_up','safety_net','concern'))}
        client=ScriptClient([{'next_action':{'type':'DONE'}},plan,plan,messages,plan],['걱정돼요']+['네']*20)
        consult(client,prepare(),Config(max_turns=45,closing_turns=8,meddb=False))
        self.assertLessEqual(50-client.turns,8)
        self.assertEqual(client.submitted['diagnosis'],'평가 중')

    def test_question_in_answer_interrupts_stale_complement(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['키가 작은 편입니다.'], 'plan':['기록을 함께 확인하겠습니다.'],
                  'follow_up':['다음 방문에 경과를 확인합니다.']}
        first={'answer':['현재 또래보다 작은 편입니다.','다른 걱정도 확인하겠습니다.']}
        second={'answer':['성장 가능성은 경과로 확인합니다.']}
        client=ScriptClient([plan,messages,first,second,plan],
                            ['걱정돼요','많이 작은 건가요?','더 클 수 있나요?']+['네']*8)
        state=self.state()
        close_consultation(Gateway(client),state,plan,12,Trace())
        actual=[e.question for e in state.evidence]
        i=actual.index(first['answer'][0])
        self.assertEqual(actual[i+1],second['answer'][0])
        self.assertNotIn(first['answer'][1],actual)
        self.assertEqual(len(state.patient_questions),2)
        self.assertTrue(all(q['answer_evidence_ids'] for q in state.patient_questions))
        self.assertTrue(all(q['status']=='answer_sent_unverified' for q in state.patient_questions))

    def test_followup_and_action_cores_survive_many_patient_questions(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['추가 평가가 필요합니다.'],'plan':['오늘 진료받으세요.'],
                  'follow_up':['내일 결과를 확인하세요.'],'safety_net':['흉통이면 즉시 응급실로 가세요.'],
                  'concern':['걱정하실 수 있습니다.']}
        answer={'answer':['확인한 범위에서 말씀드립니다.']}
        client=ScriptClient([plan,messages]+[answer]*3+[plan],['다음은 어떻게 되나요?']*20)
        state=self.state()
        close_consultation(Gateway(client),state,plan,12,Trace())
        actual=[e.question for e in state.evidence]
        for tag in ('plan','follow_up','safety_net'):
            self.assertIn(messages[tag][0],actual)
        self.assertIn('앞으로 어떻게 하실지 말씀해 주세요.',actual)
        self.assertLessEqual(len(actual),12)
        self.assertTrue(any(q['status']=='pending' for q in state.patient_questions))

    def test_concrete_fear_after_explanation_gets_a_direct_response(self):
        from nova_agent.closing import is_patient_question
        self.assertTrue(is_patient_question('줄이면 잠을 못 잘까 봐 두려워요.'))
        self.assertFalse(is_patient_question('네, 알겠습니다.'))

    def test_final_answer_is_linked_only_after_successful_say(self):
        plan={'diagnosis':'평가 중','plan':{}}
        revised={**plan,'clarification':['다음 진료에서 확인하겠습니다.'],'clarification_for':'e2'}
        client=ScriptClient([plan,revised],['걱정돼요','다음에는 어떻게 하나요?','알겠습니다'])
        state=self.state()
        close_consultation(Gateway(client),state,plan,3,Trace())
        self.assertEqual(state.patient_questions[0]['evidence_id'],'e2')
        self.assertEqual(state.patient_questions[0]['answer_evidence_ids'],['e3'])
        self.assertEqual(state.patient_questions[0]['status'],'answer_sent_unverified')

    def test_plain_text_answer_is_regenerated_for_the_same_question_before_queue(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['추가 평가가 필요합니다.'],'plan':['검사 후 계획을 정합니다.'],
                  'follow_up':['내일 결과를 확인하세요.']}
        answer={'answer':['검사 결과에 따라 결정합니다.']}
        client=ScriptClient([plan,messages,'검사 결과를 보고 결정합니다.',answer,plan],
                            ['걱정돼요','치료는 가능한가요?']+['네']*8)
        state=self.state()
        close_consultation(Gateway(client),state,plan,12,Trace())
        actual=[e.question for e in state.evidence]
        i=actual.index(messages['assessment'][0])
        self.assertEqual(actual[i+1],answer['answer'][0])
        self.assertNotIn('검사 결과를 보고 결정합니다.',actual)
        self.assertEqual(state.patient_questions[0]['attempts'],2)
        self.assertEqual(state.patient_questions[0]['status'],'answer_sent_unverified')
        self.assertIn(messages['plan'][0],actual)
        self.assertIn(messages['follow_up'][0],actual)

    def test_second_required_followup_survives_repeated_patient_questions(self):
        plan={'diagnosis':'평가 중','plan':{}}
        messages={'assessment':['성장 경과를 확인해야 합니다.'],
                  'plan':['성장 기록을 확인하겠습니다.'],
                  'follow_up':['다음 주 검사 결과를 확인해요.','세 달 후 키를 다시 재겠습니다.'],
                  'safety_net':['심한 두통이면 즉시 진료받으세요.'],
                  'essential':[{'tag':'follow_up','index':1}]}
        answer={'answer':['검사와 경과로 확인하겠습니다.','결과를 확인한 뒤 설명드리겠습니다.']}
        state=self.state()
        client=ScriptClient([plan,messages]+[answer]*3+[plan],['더 클 수 있나요?']*20)
        close_consultation(Gateway(client),state,plan,10,Trace())
        actual=[e.question for e in state.evidence]
        for text in messages['follow_up']:
            self.assertIn(text,actual)
        self.assertIn(messages['plan'][0],actual)
        self.assertIn(messages['safety_net'][0],actual)
        self.assertLessEqual(len(actual),10)

    def test_repair_cannot_reuse_essential_index_for_a_different_sentence(self):
        from nova_agent.closing import required_statements, statement_queue, TAGS
        messages={'follow_up':['가'*31], 'essential':[{'tag':'follow_up','index':1}]}
        parsed={tag:([],[]) for tag in TAGS}
        parsed['follow_up']=(['결과를 확인하겠습니다.','추가 안내입니다.'],[])
        self.assertNotIn(('follow_up','추가 안내입니다.'),required_statements(messages,parsed))
        self.assertEqual(statement_queue(messages,parsed)[0],('follow_up','결과를 확인하겠습니다.'))


if __name__=='__main__':unittest.main()
