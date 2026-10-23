import json

from nova_sdk import empty_record
from .validation import validate_record


def normalize_assessment(proposed):
    """A model-declared exposure risk is never rendered as a confirmed clinical syndrome."""
    value = dict(proposed)
    if value.get('diagnostic_basis') in {'exposure_risk_only','insufficient'}:
        value['certainty'] = 'suspected'
    diagnosis = value.get('diagnosis')
    if value.get('certainty') in {'suspected','provisional'} and isinstance(diagnosis,str) and diagnosis.strip():
        if not any(word in diagnosis for word in ('의심','미정','미확정','가능성','평가 필요','확인 필요')):
            value['diagnosis'] = diagnosis.strip()+' (의심; 추가 확인 필요)'
    return value


def make_record(state, proposed):
    """Render S/O from verbatim evidence; model supplies only assessments and future plans."""
    proposed = normalize_assessment(proposed)
    note = empty_record()
    initial = state.initial
    opening = initial.get('opening', '')
    note['S']['cc'] = str(opening)
    vitals = initial.get('vital_signs', '')
    if vitals:
        note['O']['exam'] = '시작 정보 활력징후: ' + (vitals if isinstance(vitals, str) else json.dumps(vitals, ensure_ascii=False))
    from .history import render_history
    for field, text in render_history(state, proposed).items():
        note['S'][field] = text
    cc_quote = proposed.get('chief_complaint_quote')
    if isinstance(cc_quote, str) and 1 <= len(cc_quote.strip()) <= 120 and cc_quote in str(opening):
        note['S']['cc'] = cc_quote
        note['S']['hpi'] = '초진 제공 정보: '+str(opening)+('\n'+note['S']['hpi'] if note['S']['hpi'] else '')
    exams = [f'[{e.id}, 턴 {e.turn}] {e.question}: {e.response}' for e in state.evidence if e.action == 'EXAM']
    if exams:
        note['O']['exam'] += ('\n' if note['O']['exam'] else '')+'\n'.join(exams)
    diagnosis = proposed.get('diagnosis')
    diagnosis = diagnosis.strip() if isinstance(diagnosis, str) else ''
    # Explicit uncertainty is preferable to inventing a diagnosis when the provider fails.
    diagnosis = diagnosis or '진단 미정'
    sources = {e.id: e for e in state.evidence}
    supports = []
    ids = proposed.get('evidence_ids', [])
    for eid in ids if isinstance(ids, list) else []:
        if eid == 'initial':
            supports.append('시작 정보: '+str(opening))
        elif isinstance(eid, str) and eid in sources:
            e = sources[eid]
            supports.append(f'(턴 {e.turn}) {e.question}: {e.response}')
    note['A']['evidence'] = '#1. '+diagnosis+'\n- 확보한 근거:\n'+('\n'.join(supports) if supports else '모델이 유효한 근거 ID를 제공하지 못함; 진단 불확실성 검토 필요')
    reason = proposed.get('assessment_reason')
    if supports and isinstance(reason,str) and 0 < len(reason) <= 250:
        note['A']['evidence'] += '\n판단 이유(모델 해석): '+reason
    differentials = proposed.get('differential', [])
    if isinstance(differentials, list):
        lines = []
        for d in differentials[:5]:
            if isinstance(d, dict) and isinstance(d.get('diagnosis'), str) and d['diagnosis'].strip():
                ids = d.get('evidence_ids', [])
                valid = [eid for eid in ids if isinstance(eid, str) and eid in sources] if isinstance(ids, list) else []
                reason = d.get('reason')
                rationale = ' / 모델 판단: '+reason if valid and isinstance(reason,str) and 0 < len(reason) <= 180 else ''
                lines.append('r/o '+d['diagnosis']+' (근거: '+(', '.join(valid) or '추가 확인 필요')+')'+rationale)
        note['A']['differential'] = '\n'.join(lines)
    risks = proposed.get('risk_assessment', [])
    if isinstance(risks,list):
        for risk in risks[:3]:
            if not isinstance(risk,dict) or not isinstance(risk.get('condition'),str): continue
            ids = risk.get('evidence_ids',[])
            valid = [eid for eid in ids if isinstance(eid,str) and (eid == 'initial' or eid in sources)] if isinstance(ids,list) else []
            note['A']['differential'] += ('\n' if note['A']['differential'] else '')+'위험 평가(확정 진단 아님): '+risk['condition']+' / 근거 '+(', '.join(valid) or '추가 확인 필요')
    plan = proposed.get('plan', {})
    if isinstance(plan, dict):
        for k in note['P']:
            v = plan.get(k, '')
            if isinstance(v, str):
                note['P'][k] = v
    # Provider education is a proposed plan, never evidence that teaching happened.
    planned = note['P']['education'].strip()
    actual = state.delivered_explanations()
    parts = []
    if actual:
        parts.append('실제 전달한 SAY 원문(내용의 충분성은 별도 검토):\n'+'\n'.join(
            f'[{e.id}, 턴 {e.turn}] {e.question}' for e in actual))
    else:
        parts.append('태그로 연결된 실제 설명 SAY 없음; 교육 완료로 간주하지 않음')
    teach_back = [e for e in state.evidence if 'teach_back' in e.communication]
    if teach_back:
        parts.append('실제 이해 확인 응답(이해 충분성 별도 검토):\n'+'\n'.join(
            f'[{e.id}, 턴 {e.turn}] {e.question} / 환자: {e.response}' for e in teach_back))
    if planned:
        parts.append('추가 교육 계획(수행 확인 아님):\n'+planned)
    note['P']['education'] = '\n\n'.join(parts)
    # Bound oversized provider responses without silently changing their meaning.
    for section in note.values():
        for key, text in section.items():
            raw = text.encode('utf-8')
            if len(raw) > 5900:
                section[key] = raw[:5800].decode('utf-8', errors='ignore')+'\n[분량 제한으로 원문 일부 생략; 전체는 실행 로그 참조]'
    validate_record(note, diagnosis)
    return note, diagnosis
