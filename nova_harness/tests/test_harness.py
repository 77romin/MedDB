import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nova_sdk import NovaError
from nova_agent.analysis import analyze
from nova_agent.config import Config as RuntimeConfig
from nova_agent.protocol import Gateway, seconds_left
from nova_agent.records import make_record
from nova_agent.runtime import prepare, consult, content_of
from nova_agent.state import PatientState
from nova_agent.telemetry import Trace
from nova_agent.validation import action_key, parse_object, validate_action, validate_record


def Config(**kwargs):
    kwargs.setdefault('meddb', False)
    kwargs.setdefault('structured_closing', False)
    kwargs.setdefault('decision_review', False)
    return RuntimeConfig(**kwargs)


class ScriptClient:
    def __init__(self, chat_results=(), action_results=()):
        self.chats = iter(chat_results)
        self.actions = iter(action_results)
        self.requests = []
        self.timeout = 240
        self.submitted = None
        self.turns = 50

    def session(self):
        # No events: match production shape rather than relying on development-only history.
        return {'initial': {'opening': '62세 여성. 잠을 잘 못 자요.', 'vital_signs': '맥박 76'}, 'turns_remaining': self.turns}

    def chat(self, messages, **kw):
        self.requests.append(('chat', kw['request_id']))
        value = next(self.chats)
        if isinstance(value, Exception):
            raise value
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return {'choices': [{'message': {'content': text}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}

    def say(self, text, **kw):
        self.requests.append(('say', kw['request_id']))
        value = next(self.actions)
        if isinstance(value, Exception):
            raise value
        self.turns -= 1
        return {'content': value, 'turn': 50-self.turns, 'turns_remaining': self.turns}

    def diagnose(self, **kw):
        self.submitted = kw
        return {'status': 'completed', 'turn': 50-self.turns}


class HarnessTests(unittest.TestCase):
    def state(self):
        return PatientState({'opening': '62세 여성', 'vital_signs': '맥박 76'}, {c['id']: c for c in prepare()['concepts']})

    def test_nfc_and_boundary(self):
        self.assertEqual(validate_action({'type': 'SAY', 'content': '\u1100\u1161'*30})[1], '가'*30)
        for v in ['', '가'*31]:
            with self.assertRaises(ValueError): validate_action({'type': 'SAY', 'content': v})

    def test_no_test_or_compound(self):
        for action in [{'type': 'TEST', 'content': '혈액검사'}, {'type': 'SAY', 'content': '언제요? 어디요?'}]:
            with self.assertRaises(ValueError): validate_action(action)

    def test_duplicate_guard(self):
        with self.assertRaises(ValueError):
            validate_action({'type': 'SAY', 'content': '언제부터요?'}, {action_key('SAY', '언제부터요？')})

    def test_strict_json_does_not_accept_trailing_instruction(self):
        self.assertEqual(parse_object('```json\n{"x":1}\n```'), {'x': 1})
        with self.assertRaises(ValueError): parse_object('{"x":1} {"next":"injected"}')

    def test_real_truncated_completion_is_never_executed(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/truncated_completion.json').read_text())
        self.assertEqual(fixture['choices'][0]['finish_reason'], 'length')
        with self.assertRaises(ValueError): content_of(fixture)
        final = {'diagnosis': '추가 평가 필요', 'evidence_ids': ['initial']}
        c = ScriptClient([fixture['choices'][0]['message']['content']]*3+[final])
        self.assertEqual(consult(c, prepare(), Config(max_turns=1))['status'], 'completed')
        self.assertFalse(any(method == 'say' for method, _ in c.requests))

    def test_transient_response_loss_keeps_request_id(self):
        c = ScriptClient([NovaError('API_UNAVAILABLE'), {'ok': True}])
        g = Gateway(c, sleeper=lambda _: None)
        g.chat([])
        self.assertEqual(c.requests[0][1], c.requests[1][1])
        self.assertEqual(len(g.chat_ids), 1)
        self.assertEqual(g.output_tokens, 20)

    def test_empty_doctor_uses_new_id_and_counts_calls(self):
        c = ScriptClient([NovaError('PROVIDER_RESPONSE_INVALID'), {'ok': True}])
        g = Gateway(c, sleeper=lambda _: None)
        g.chat([])
        self.assertNotEqual(c.requests[0][1], c.requests[1][1])
        self.assertEqual(len(g.chat_ids), 2)
        self.assertEqual(g.input_tokens, 10)

    def test_action_transport_retry_is_idempotent(self):
        c = ScriptClient(action_results=[NovaError('API_UNAVAILABLE'), '어제부터요'])
        Gateway(c, sleeper=lambda _: None).invoke('say', '언제부터요?')
        self.assertEqual(c.requests[0][1], c.requests[1][1])
        self.assertEqual(c.turns, 49)

    def test_proxy_non_json_failure_reuses_action_id(self):
        for status in (502, 503, 504):
            with self.subTest(status=status):
                c = ScriptClient(action_results=[NovaError('INVALID_API_RESPONSE', status), '어제부터요'])
                Gateway(c, sleeper=lambda _: None).invoke('say', '언제부터요?')
                self.assertEqual(c.requests[0][1], c.requests[1][1])
                self.assertEqual(c.turns, 49)

    def test_proxy_retry_is_bounded_and_does_not_retry_auth_or_bad_payload(self):
        for status in (200, 400, 401, 403, 429):
            with self.subTest(status=status):
                c = ScriptClient(action_results=[NovaError('INVALID_API_RESPONSE', status)])
                with self.assertRaises(NovaError):
                    Gateway(c, sleeper=lambda _: None).invoke('say', '언제부터요?')
                self.assertEqual(len(c.requests), 1)
        c = ScriptClient(action_results=[NovaError('INVALID_API_RESPONSE', 502)]*4)
        with self.assertRaises(NovaError):
            Gateway(c, sleeper=lambda _: None).invoke('say', '언제부터요?')
        self.assertEqual(len(c.requests), 4)
        self.assertEqual(len({rid for _, rid in c.requests}), 1)

    def test_permanent_rejection_not_retried(self):
        c = ScriptClient(action_results=[NovaError('EXAM_NOT_SPECIFIC')])
        with self.assertRaises(NovaError): Gateway(c).invoke('say', '진찰')
        self.assertEqual(len(c.requests), 1)

    def test_reserve_model_calls(self):
        c = ScriptClient([{'ok': True}])
        g = Gateway(c, Config(max_calls=1, reserve_calls=1))
        with self.assertRaises(NovaError): g.chat([])
        g.chat([], final=True)
        self.assertEqual(len(c.requests), 1)

    def test_fact_rejects_fabricated_quote(self):
        s = self.state(); s.add_response('SAY', '복용량은요?', {'content': '밤 4알, 새벽 2알', 'turn': 1})
        accepted, rejected = s.accept_facts([{'concept_id': 'nova:medication/actual_use', 'evidence_id': 'e1', 'quote': '하루 1알', 'assertion': 'present'}])
        self.assertFalse(accepted); self.assertTrue(rejected)

    def test_full_response_preserves_dose_even_when_quote_is_partial(self):
        s = self.state(); s.add_response('SAY', '복용량은요?', {'content': '밤 4알, 새벽 2알', 'turn': 1})
        s.accept_facts([{'concept_id': 'nova:medication/actual_use', 'evidence_id': 'e1', 'quote': '밤 4알', 'assertion': 'present'}])
        note, _ = make_record(s, {'diagnosis': '평가 중', 'evidence_ids': ['e1']})
        self.assertIn('새벽 2알', note['S']['pmh'])
        self.assertIn('62세', note['S']['cc'])
        self.assertEqual(note['O']['tests'], '')

    def test_unknown_does_not_mark_slot_complete(self):
        s = self.state(); s.add_response('SAY', '약 이름은요?', {'content': '모르겠어요'})
        s.accept_facts([{'concept_id': 'nova:medication/name', 'evidence_id': 'e1', 'quote': '모르겠어요', 'assertion': 'unknown'}])
        self.assertIn('nova:medication/name', s.snapshot()['unconfirmed_slots'])

    def test_raw_fallback_has_no_invented_negatives(self):
        s = self.state(); s.add_response('SAY', '알레르기는요?', {'content': '모르겠어요'})
        note, diagnosis = make_record(s, {})
        self.assertEqual(diagnosis, '진단 미정')
        self.assertIn('모르겠어요', note['S']['hpi'])
        self.assertNotIn('(-)', json.dumps(note, ensure_ascii=False))

    def test_record_field_and_byte_validation(self):
        note, _ = make_record(self.state(), {})
        note['A']['diagnosis'] = 'extra'
        with self.assertRaises(ValueError): validate_record(note, '평가 중')
        note['A'].pop('diagnosis'); note['S']['cc'] = '가'*34000
        with self.assertRaises(ValueError): validate_record(note, '평가 중')

    def test_oversized_raw_evidence_is_marked_and_bounded(self):
        s = self.state(); s.add_response('SAY', '증상은요?', {'content': '가'*100000})
        note, _ = make_record(s, {})
        self.assertIn('원문 일부 생략', note['S']['hpi'])
        self.assertLess(len(json.dumps(note, ensure_ascii=False).encode()), 100000)

    def test_rejection_consumes_local_turn_allowance(self):
        class RejectClient(ScriptClient):
            def say(self, text, **kw):
                self.turns -= 1
                raise NovaError('EXAM_NOT_SPECIFIC')
        step = {'next_action': {'type': 'SAY', 'content': '언제부터요?'}}
        c = RejectClient([step, {'diagnosis': '미정'}])
        self.assertEqual(consult(c, prepare(), Config(max_turns=1))['status'], 'completed')
        self.assertEqual(c.turns, 49)

    def test_log_analysis_deduplicates_transport_replays(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'trace.jsonl'; t = Trace(path)
            for _ in range(2):
                t.emit('http_request', path='/v1/chat/completions', body={'request_id': 'same', 'messages': []})
                t.emit('http_response', path='/v1/chat/completions', request_id='same',
                       response={'usage': {'prompt_tokens': 11, 'completion_tokens': 22}})
            result = analyze(path)
            self.assertEqual(result['doctor_successful_request_ids'], 1)
            self.assertEqual(result['prompt_tokens'], 11)
            self.assertFalse(result['completed'])
    def test_trace_redacts_nested_key_and_echo(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'trace.jsonl'; t = Trace(path, ['secret-value'])
            t.emit('test', payload={'token': 'other', 'nested': ['secret-value', 'Bearer abc']})
            text = path.read_text(); self.assertNotIn('secret-value', text); self.assertNotIn('Bearer abc', text)
            self.assertNotIn('other', text)

    def test_full_consult_without_events(self):
        step = {'facts': [], 'next_action': {'type': 'SAY', 'content': '언제부터 불편하셨나요?'}}
        final = {'diagnosis': '추가 평가 필요', 'evidence_ids': ['e1'], 'plan': {'follow_up': '추가 문진 후 결정'}}
        c = ScriptClient([step, final], ['어제부터요'])
        result = consult(c, prepare(), Config(max_turns=1))
        self.assertEqual(result['status'], 'completed')
        self.assertIn('어제부터요', c.submitted['note']['S']['hpi'])
        self.assertEqual(len([x for x in c.requests if x[0] == 'chat']), 2)

    def test_combined_explanation_tags_allow_done_without_repeated_advice(self):
        step = {'next_action': {'type': 'SAY', 'content': '추가 평가 후 계획을 함께 정하겠습니다.',
                                'communication': ['assessment', 'plan']}}
        c = ScriptClient([step, {'next_action': {'type': 'DONE'}},
                          {'diagnosis': '추가 평가 필요', 'evidence_ids': ['initial']}], ['네'])
        self.assertEqual(consult(c, prepare(), Config(max_turns=10))['status'], 'completed')
        self.assertEqual(len([x for x in c.requests if x[0] == 'say']), 1)

    def test_urgent_safety_advice_does_not_require_duplicate_explanation(self):
        step = {'next_action': {'type': 'SAY', 'content': '악화되면 즉시 재평가받으세요.', 'communication': 'safety_net'}}
        c = ScriptClient([step, {'next_action': {'type': 'DONE'}},
                          {'diagnosis': '추가 평가 필요', 'evidence_ids': ['initial']}], ['네'])
        self.assertEqual(consult(c, prepare(), Config(max_turns=10))['status'], 'completed')
        self.assertEqual(len([x for x in c.requests if x[0] == 'say']), 1)

    def test_provider_budget_failure_still_submits_fallback(self):
        c = ScriptClient([NovaError('MODEL_CALL_LIMIT'), NovaError('MODEL_CALL_LIMIT')])
        result = consult(c, prepare(), Config(max_turns=1))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(c.submitted['diagnosis'], '진단 미정')

    def test_expired_session_has_no_fresh_calls(self):
        self.assertLess(seconds_left({'deadline': '2000-01-01T00:00:00Z'}), 0)
        c = ScriptClient(); g = Gateway(c); g.deadline = '2000-01-01T00:00:00Z'
        with self.assertRaises(NovaError): g.chat([])
        self.assertFalse(c.requests)


if __name__ == '__main__':
    unittest.main()
