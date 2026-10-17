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
    def state(self):
        return PatientState({'opening':'환자 시작 정보'}, {c['id']:c for c in prepare()['concepts']})

    def test_complete_sentence_selection_does_not_truncate(self):
        self.assertEqual(short_statement('검사로 확인할게요. 결과를 확인하고 계획을 함께 정하겠습니다.'),'검사로 확인할게요.')
        self.assertIsNone(short_statement('가'*31))
        self.assertIsNone(short_statement('무슨 약인가요?'))

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


if __name__=='__main__':unittest.main()
