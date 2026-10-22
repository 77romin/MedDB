"""Conservative source-linked delivery state, independent of model completion claims."""
from copy import deepcopy
import hashlib
import re
import unicodedata

FIELDS = ('education', 'disposition', 'follow_up', 'treatment', 'tests')


def canonical(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def has_prohibition(text):
    # Korean prohibitions inflect: 하지 않도록 -> 하지 마세요, 피하도록 -> 피해 주세요.
    # '말씀' alone is not a prohibition.
    return bool(re.search(r'지\s*(?:않|말|마(?:세|십|셔))|금지|피하|피해', text))


def complete_message(text):
    return (isinstance(text, str) and 0 < len(text) <= 30 and '?' not in text
            and bool(re.search(r'(세요|어요|아요|니다|게요|돼요|해요)[.!。]?$', text))
            and bool(re.search('[가-힣]', text))
            and not re.search('[\u3040-\u30ff]', text))


class ObligationLedger:
    def __init__(self):
        self.versions = []
        self.events = []
        self.rejections = []

    def update(self, note, observation_hash=None, record_count=None):
        plan = {k: v.split('환자에게 설명함:', 1)[0].strip()
                for k, v in note.get('P', {}).items() if isinstance(v, str)}
        if self.versions and self.versions[-1]['plan'] == plan:
            return
        previous = self.versions[-1] if self.versions else None
        self.versions.append({'version': len(self.versions) + 1, 'plan': deepcopy(plan),
                              'observation_hash': observation_hash, 'record_count': record_count or len(self.versions) + 1,
                              'obligations': [dict(deepcopy(r), state='generated', delivery_events=[])
                                              for r in previous['obligations']
                                              if r['source_quote'] in plan.get(r['source_field'], '')] if previous else [],
                              'changed_fields': [k for k in set(plan) | set(previous['plan'] if previous else {})
                                                 if not previous or plan.get(k) != previous['plan'].get(k)],
                              'change_reason': 'new_record; clinical reason requires review' if previous else 'initial_record'})

    def register(self, payload):
        if not self.versions or not isinstance(payload, dict):
            raise ValueError('missing plan or payload')
        version = self.versions[-1]
        rows = payload.get('obligations')
        if not isinstance(rows, list) or len(rows) > 12:
            raise ValueError('invalid obligations')
        accepted = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('invalid obligation')
            field, quote = row.get('source_field'), row.get('source_quote')
            if field not in FIELDS or not isinstance(quote, str) or not quote.strip() or quote not in version['plan'].get(field, ''):
                raise ValueError('unsupported quote')
            condition, action = row.get('condition'), row.get('action')
            if not isinstance(condition, str) or not isinstance(action, str) or not action.strip():
                raise ValueError('missing condition/action')
            if not condition and re.search(r'경우|생기면|있으면| 시[ ,.]|때|복용 후', quote):
                raise ValueError('conditional source without condition')
            if action not in quote or (condition and condition not in quote):
                raise ValueError('invented anchors')
            # Conditional/negative language cannot disappear in the generated group.
            messages = row.get('messages')
            if not isinstance(messages, list) or not 1 <= len(messages) <= 3 or not all(complete_message(m) for m in messages):
                raise ValueError('incomplete message')
            joined = canonical(' '.join(messages))
            if canonical(action) not in joined or (condition and canonical(condition) not in joined):
                raise ValueError('lost condition/action')
            if has_prohibition(quote) and not has_prohibition(joined):
                raise ValueError('lost negation')
            for marker in ('즉시', '응급'):
                if marker in quote and marker not in joined:
                    raise ValueError('lost source qualifier')
            if set(re.findall(r'\d+(?:\.\d+)?', joined)) - set(re.findall(r'\d+(?:\.\d+)?', quote)):
                raise ValueError('new number')
            timing = row.get('timing', '')
            if not isinstance(timing, str) or (timing and (timing not in quote or canonical(timing) not in joined)):
                raise ValueError('lost timing')
            priority = row.get('priority')
            applicability = row.get('applicability')
            if priority not in ('critical', 'routine') or applicability not in ('current', 'conditional'):
                raise ValueError('invalid classification')
            identity = hashlib.sha256((field + '\0' + quote + '\0' + condition + '\0' + action).encode()).hexdigest()[:20]
            if any(x['id'] == identity for x in accepted):
                continue
            accepted.append({'id': identity, 'source_field': field, 'source_quote': quote,
                             'condition': condition, 'action': action, 'timing': timing,
                             'negation_source': quote if has_prohibition(quote) else '',
                             'priority': priority,
                             'applicability': applicability, 'messages': list(messages),
                             'state': 'generated', 'delivery_events': []})
        version['obligations'] = accepted
        version['extraction_complete'] = False  # A model subset is never a completeness proof.
        return accepted

    def register_partial(self, payload):
        """Accept complete independent rows; never relax one row's constraints."""
        if not isinstance(payload, dict) or not isinstance(payload.get('obligations'), list) or len(payload['obligations']) > 12:
            raise ValueError('invalid obligations')
        if not self.versions:
            raise ValueError('missing plan')
        version = self.versions[-1]
        accepted = deepcopy(version['obligations'])
        rejected = []
        for index, row in enumerate(payload['obligations']):
            try:
                valid = self.register({'obligations': [row]})
                for item in valid:
                    if not any(old['id'] == item['id'] for old in accepted):
                        accepted.append(item)
            except (ValueError, TypeError, KeyError) as exc:
                rejected.append({'index': index, 'row': deepcopy(row), 'reason': str(exc)})
            finally:
                version['obligations'] = accepted
        self.rejections.extend(deepcopy(rejected))
        return accepted, rejected

    def audit(self, speech):
        for version in self.versions:
            for row in version['obligations']:
                # Do not credit speech predating this version's record.
                matches = [s for s in speech if s.get('record_count', 0) >= version['record_count']
                           and s['content'] in row['messages']]
                row['delivery_events'] = [s['index'] for s in matches]
                row['state'] = ('sent_success' if all(any(s['content'] == m for s in matches)
                                                    for m in row['messages']) else 'unresolved')
        current = self.versions[-1] if self.versions else None
        return deepcopy({'versions': self.versions,
                         'unresolved_ids': [r['id'] for r in current['obligations'] if r['state'] != 'sent_success'] if current else [],
                         'coverage_verified': False,
                         'unverified_plan_fields': list(current['plan']) if current else [],
                         'understanding': 'not_inferred_from_delivery',
                         'plan_changed_after_speech': bool(current and current['version'] > 1 and speech),
                         'rejected_items': self.rejections, 'events': self.events})

    def render(self, note, speech):
        out = deepcopy(note)
        plan = out.setdefault('P', {})
        # Keep source content as explicitly attributed draft, never an asserted execution.
        for field, value in list(plan.items()):
            if isinstance(value, str):
                value = value.split('환자에게 설명함:', 1)[0].strip()
                plan[field] = '계획 원안 인용(수행 여부 미확인):\n' + value
        actual = [s for s in speech if s.get('record_count', 0) > 0 and '?' not in s['content']]
        lines = ['실제 전달 기록(API 성공 응답 기준; 이해 여부 미확인):']
        lines.extend('[발화 {0}, 요청 {1}] {2}'.format(s['index'], s.get('request_id') or '미기록', s['content']) for s in actual)
        if not actual:
            lines.append('확인된 전달 없음.')
        audit = self.audit(speech)
        lines.append('추출된 의무 중 미확인 전달 항목 수: ' + str(len(audit['unresolved_ids'])))
        lines.append('추출 누락과 임상 적절성은 미검증이며, 0건도 전체 안내 완료를 뜻하지 않음.')
        if audit['plan_changed_after_speech']:
            lines.append('설명 이후 계획 변경 있음: 변경 내용의 재설명 여부 별도 확인 필요.')
        plan['education'] = plan.get('education', '') + '\n' + '\n'.join(lines)
        return out
