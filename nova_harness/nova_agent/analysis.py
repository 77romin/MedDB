"""Log-derived diagnostics, not official clinical scores."""
import json
from collections import Counter
from pathlib import Path


def analyze(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    finished = any(r['event'] in {'experiment_complete', 'experiment_failed'} for r in rows)
    errors = Counter(r['code'] for r in rows if r['event'] == 'http_error')
    responses = [r for r in rows if r['event'] == 'http_response']
    chats, actions, final = {}, {}, None
    latency = []
    for r in responses:
        value = r['response']
        if r['path'].endswith('/chat/completions'):
            chats[r['request_id']] = value
        elif r['path'].endswith('/actions'):
            actions[r['request_id']] = value
        latency.append(r.get('seconds', 0))
    for r in rows:
        if r['event'] == 'http_request' and isinstance(r.get('body'), dict) and r['body'].get('action') == 'DIAGNOSE':
            final = r['body']
    rejected = [code for code in errors if code in {'EXAM_NOT_SPECIFIC', 'EXAM_NOT_RECOGNIZED', 'CONTENT_TOO_LONG', 'EMPTY_CONTENT'}]
    findings = []
    if rejected:
        findings.append({'category': 'action_rejection', 'evidence': {k: errors[k] for k in rejected},
                         'next_step': '진찰 목적과 구체적 동작을 검토하고 거절된 표현을 회귀 시나리오에 추가'})
    invalid = [r for r in rows if r['event'] == 'validation_error']
    if invalid:
        findings.append({'category': 'model_output_contract', 'count': len(invalid),
                         'next_step': '원문 출력과 validation_error를 대조해 프롬프트·파싱·중복 정책을 수정'})
    if errors.get('PROVIDER_RESPONSE_INVALID'):
        findings.append({'category': 'empty_doctor_output', 'count': errors['PROVIDER_RESPONSE_INVALID'],
                         'next_step': '추론 강도와 출력 한도를 동일 증례에서 비교; 재시도 ID 정책 확인'})
    truncated = sum(bool(isinstance(c.get('choices'), list) and c['choices']
                         and isinstance(c['choices'][0], dict) and c['choices'][0].get('finish_reason') == 'length')
                    for c in chats.values())
    if truncated:
        findings.append({'category': 'output_truncation', 'count': truncated,
                         'next_step': '이전 사실 재출력을 제거하고 새 응답의 사실만 출력. 출력 한도 증가 전 구조를 간소화하고 동일 조건 재평가'})
    missing = []
    if final:
        for section in ('S', 'A', 'P'):
            missing.extend(f'{section}.{k}' for k, v in final.get('note', {}).get(section, {}).items() if not str(v).strip())
        if missing:
            findings.append({'category': 'empty_note_fields', 'fields': missing,
                             'next_step': '미확인·미수행이 정당한지 확인; 계획 필드는 실제 임상 필요와 대조. 빈 칸을 허위 사실로 채우지 않음'})
    elif finished:
        findings.append({'category': 'no_submission_attempt', 'next_step': '실행 예외·시간·모델 예산과 종료 경로를 우선 점검'})
    completed_ids = {r['request_id'] for r in responses if isinstance(r.get('response'), dict)
                     and r['response'].get('status') == 'completed' and r['path'].endswith('/actions')}
    result = {
        'scope': 'log-derived diagnostics; no official score and no validated diagnosis correctness',
        'experiment_finished': finished,
        'collection_stop_reason': next((r.get('reason') for r in reversed(rows) if r['event'] == 'collection_finished'), None),
        'completed': bool(completed_ids), 'doctor_successful_request_ids': len(chats),
        'doctor_attempted_request_ids': len({r.get('body', {}).get('request_id') for r in rows
                                            if r['event'] == 'http_request' and r['path'].endswith('/chat/completions')}),
        'prompt_tokens': sum(c.get('usage', {}).get('prompt_tokens', 0) for c in chats.values()),
        'completion_tokens': sum(c.get('usage', {}).get('completion_tokens', 0) for c in chats.values()),
        'action_success_responses': len(actions), 'max_server_turn': max([v.get('turn', 0) or 0 for v in actions.values()]+[0]),
        'errors': dict(errors), 'validation_errors': len(invalid),
        'truncated_completions': truncated,
        'returned_models': sorted({c['model'] for c in chats.values() if isinstance(c.get('model'), str)}),
        'closure_reviews': sum(r['event'] == 'closure_review' for r in rows),
        'closure_followups': sum(r['event'] == 'closure_followup' for r in rows),
        'patient_compound_refusals': sum('한 번에 하나씩' in str(v.get('content', '')) for v in actions.values()),
        'elapsed_seconds': round(rows[-1]['monotonic']-rows[0]['monotonic'], 3) if rows else 0,
        'http_wait_seconds': round(sum(latency), 3), 'diagnosis': final.get('diagnosis') if final else None,
        'findings': findings,
    }
    return result


def write_report(trace_path):
    path = Path(trace_path)
    result = analyze(path)
    path.with_name('analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# 실행 로그 분석', '', result['scope'], '',
             f"- 제출 완료 응답: {result['completed']}", f"- 주진단: {result['diagnosis']}",
             f"- Doctor 고유 요청: {result['doctor_attempted_request_ids']} / 성공 {result['doctor_successful_request_ids']}",
             f"- 입력/출력 토큰: {result['prompt_tokens']} / {result['completion_tokens']}",
             f"- 최대 확인 서버 턴: {result['max_server_turn']}", f"- 실행 시간: {result['elapsed_seconds']}초", '',
             '임상 적절성·정답 일치·공식 영역 점수는 이 분석만으로 판정하지 않습니다.', '']
    for finding in result['findings']:
        lines += ['## '+finding['category'], '', json.dumps(finding, ensure_ascii=False, indent=2), '']
    path.with_name('analysis.md').write_text('\n'.join(lines), encoding='utf-8')
    return result
