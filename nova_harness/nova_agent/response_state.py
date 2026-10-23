"""R3a experiment: observed replies are not automatically completed history slots.

No facts or diagnoses are inferred here. Raw observations remain in the original
transcript/coverage records. This overlay changes only bounded question handling.
"""
import re
import unicodedata

AMBIGUOUS = re.compile(r'모르겠|몰라|모릅|잘\s*모르|기억(?:이|나지|하지|이\s*잘).*않|기억.*안\s*나|무슨\s*(?:뜻|말)|못\s*들|다시\s*(?:말|질문)|대답.*어려')
DECLINED = re.compile(r'말하.*싫|답하.*싫|대답.*싫|말씀.*어려|답변.*거부|비밀')
# Only explicit numeric-unit questions get completeness checks; qualitative
# histories remain received, never asserted medically normal/negative.
QUANTITATIVE = {
    'sleep_hours': (r'(?:\d+(?:\.\d+)?|[일이삼사오육칠팔구십백]+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|서너|대여섯|반)\s*시간|전혀.*못|한숨.*못', '실제 수면 시간을 대략 알려주시겠어요?'),
    'sleep_latency': (r'(?:\d+(?:\.\d+)?|[일이삼사오육칠팔구십백]+|한|두|세|네|다섯|여섯|서너|대여섯|반)\s*(?:분|시간)|바로|금방|즉시', '잠들기까지 대략 몇 분 걸리나요?'),
    'sleep_frequency': (r'(?:\d+|[일이삼사오육칠팔구십]+|한|두|세|네|다섯|여섯|일곱|서너)\s*(?:일|번)|매일|날마다|매번', '일주일에 대략 며칠인가요?'),
}


def key(text):
    text = unicodedata.normalize('NFC', str(text))
    text = re.sub(r'^많이 힘드셨겠어요[.!]?\s*', '', text)
    return re.sub(r'[\s?.!。？！]', '', text)


def classify(target, answer):
    if not answer.strip(): return 'ambiguous'
    if DECLINED.search(answer): return 'declined'
    if AMBIGUOUS.search(answer): return 'ambiguous'
    rule = QUANTITATIVE.get(target)
    if rule and not re.search(rule[0], answer): return 'partial'
    return 'received'  # Not a clinical assertion or a verified complete answer.


def install(events):
    from meddb import coverage
    original = coverage.CareCoverage

    class ResponseCoverage(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.response_history = []
            self.response_slots = {}
            self.answered_wording = set()
            self.clarification_attempted = set()

        def observe(self, target, question, answer, turn):
            super().observe(target, question, answer, turn)
            state = classify(target, answer)
            row = {'target': target, 'question': question, 'answer': answer,
                   'turn': turn, 'status': state}
            self.response_history.append(row)
            if target:
                self.response_slots[target] = row
            if state == 'received' and (target or '?' in question):
                self.answered_wording.add(key(question))
            events.append({'event': 'response_observed', 'target': target,
                           'turn': turn, 'status': state})

        def needed(self, kb):
            # Base filtering of demographics, exams, risk and required histories
            # remains unchanged. Do not remove kb.asked or rewrite clinical facts.
            actions = []
            for action in super().needed(kb):
                if action['type'] == 'SAY' and key(action['text']) in self.answered_wording:
                    events.append({'event': 'answered_filtered', 'stage': 'required',
                                   'target': action.get('target')})
                else:
                    actions.append(action)
            for target, row in self.response_slots.items():
                if row['status'] not in ('ambiguous', 'partial') or target in self.clarification_attempted:
                    continue
                if self.attempts.get(target, 0) >= 2:
                    continue
                rule = QUANTITATIVE.get(target)
                question = rule[1] if rule else '기억나는 범위에서 ' + row['question']
                if len(unicodedata.normalize('NFC', question)) > 30:
                    events.append({'event': 'clarification_unavailable', 'target': target})
                    continue
                if key(question) == key(row['question']):
                    continue
                # Risk clarification retains risk precedence; other clarification
                # follows onset/urgent questions instead of pre-empting them all.
                priority = 0 if target in getattr(kb, 'conflicts', ()) else 2
                actions.append({'type': 'SAY', 'text': question, 'target': target,
                                'resolves': [], 'priority': priority,
                                'why': '실제 모호/부분 답변 명확화', '_response_clarification': True})
            for target in getattr(kb, 'conflicts', ()):
                if target in self.response_slots:
                    events.append({'event': 'observed_conflict', 'target': target})
            return sorted(actions, key=lambda a: a['priority'])

        def trace(self):
            result = super().trace()
            result['response_state'] = {'history': self.response_history,
                                        'slots': self.response_slots,
                                        'clarification_attempted': sorted(self.clarification_attempted)}
            return result

        def allow_action(self, kb, kind, text, target):
            if kind == 'SAY' and key(text) in self.answered_wording:
                events.append({'event': 'answered_filtered', 'stage': 'generated', 'target': target})
                return False
            return super().allow_action(kb, kind, text, target)

    # Count actual observed clarification, not proposals from needed().
    observe = ResponseCoverage.observe
    def observe_with_attempt(self, target, question, answer, turn):
        previous = self.response_slots.get(target)
        if previous and previous['status'] in ('ambiguous', 'partial'):
            self.clarification_attempted.add(target)
            events.append({'event': 'clarification_observed', 'target': target, 'turn': turn})
        observe(self, target, question, answer, turn)
    ResponseCoverage.observe = observe_with_attempt
    coverage.CareCoverage = ResponseCoverage
    return original


def restore(original):
    from meddb import coverage
    coverage.CareCoverage = original
