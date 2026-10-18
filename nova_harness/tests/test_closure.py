import json
import unittest

from nova_sdk import NovaError
from nova_agent.closure import review_closure
from nova_agent.config import Config as RuntimeConfig
from nova_agent.protocol import Gateway
from nova_agent.runtime import consult, prepare
from nova_agent.state import PatientState
from test_harness import ScriptClient


def done():
    return {'next_action': {'type': 'DONE'}}


def initial_steps():
    return [{'next_action': {'type': 'SAY', 'content': f'{i}번 항목은 어떤가요?',
                            'communication': ['plan'] if i == 5 else []}} for i in range(1, 6)]


def Config(**kwargs):
    kwargs.setdefault('meddb', False)
    kwargs.setdefault('structured_closing', False)
    kwargs.setdefault('decision_review', False)
    return RuntimeConfig(**kwargs)


class ClosureTests(unittest.TestCase):
    def test_review_rejects_non_boolean_readiness(self):
        state = PatientState({}, {})
        client = ScriptClient([{'ready': 'false', 'urgent_exit': False, 'missing': []}])
        with self.assertRaises(ValueError): review_closure(Gateway(client), state, [])

    def test_review_rejects_duplicate_action(self):
        from nova_agent.validation import action_key
        state = PatientState({}, {}); state.seen.add(action_key('SAY', '언제부터요?'))
        client = ScriptClient([{'ready': False, 'urgent_exit': False, 'missing': ['시작 시점'],
                                'next_action': {'type': 'SAY', 'content': '언제부터요?'}}])
        with self.assertRaises(ValueError): review_closure(Gateway(client), state, [])

    def test_followup_once_then_finish(self):
        audit = {'ready': False, 'urgent_exit': False, 'missing': ['경과 변화'],
                 'reason': '한 번 더 확인하면 판단이 달라질 수 있음',
                 'next_action': {'type': 'SAY', 'content': '최근에는 어떻게 변했나요?'}}
        client = ScriptClient(initial_steps()+[done(), audit, done(), {'diagnosis': '추가 평가 필요'}], ['네']*6)
        self.assertEqual(consult(client, prepare(), Config(max_turns=20, closure_audit=True))['status'], 'completed')
        self.assertEqual(len([r for r in client.requests if r[0] == 'say']), 6)
        self.assertEqual(len([r for r in client.requests if r[0] == 'chat']), 9)

    def test_urgent_exit_does_not_add_questions(self):
        audit = {'ready': False, 'urgent_exit': True, 'reason': '즉시 처치 지연 방지', 'missing': []}
        client = ScriptClient(initial_steps()+[done(), audit, {'diagnosis': '추가 평가 필요'}], ['네']*5)
        self.assertEqual(consult(client, prepare(), Config(max_turns=20, closure_audit=True))['status'], 'completed')
        self.assertEqual(len([r for r in client.requests if r[0] == 'say']), 5)

    def test_invalid_review_does_not_block_submission(self):
        client = ScriptClient(initial_steps()+[done(), 'invalid JSON', {'diagnosis': '추가 평가 필요'}], ['네']*5)
        self.assertEqual(consult(client, prepare(), Config(max_turns=20, closure_audit=True))['status'], 'completed')

    def test_ablation_does_not_call_reviewer(self):
        client = ScriptClient(initial_steps()+[done(), {'diagnosis': '추가 평가 필요'}], ['네']*5)
        self.assertEqual(consult(client, prepare(), Config(max_turns=20, closure_audit=False))['status'], 'completed')
        self.assertEqual(len([r for r in client.requests if r[0] == 'chat']), 7)

    def test_small_turn_reserve_skips_review(self):
        client = ScriptClient(initial_steps()+[done(), {'diagnosis': '추가 평가 필요'}], ['네']*5)
        self.assertEqual(consult(client, prepare(), Config(max_turns=10, closure_audit=True))['status'], 'completed')
        self.assertEqual(len([r for r in client.requests if r[0] == 'chat']), 7)


if __name__ == '__main__': unittest.main()
