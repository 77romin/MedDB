import unittest
import json
from pathlib import Path

from nova_agent.closing import close_consultation, short_statement
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
        self.assertIn(short['assessment'],revised['plan']['education'])
        self.assertNotIn('가'*40,revised['plan']['education'])
        self.assertEqual(left,4)

    def test_unavailable_generation_does_not_claim_unsent_education(self):
        from nova_sdk import NovaError
        plan={'diagnosis':'평가 중','plan':{}}
        client=ScriptClient([plan,NovaError('MODEL_CALL_LIMIT'),plan],['모르겠어요','네'])
        revised,_=close_consultation(Gateway(client),self.state(),plan,8,Trace())
        self.assertNotIn('실제 SAY 설명',revised['plan'].get('education',''))


if __name__=='__main__':unittest.main()
