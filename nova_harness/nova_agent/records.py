import json

from nova_sdk import empty_record
from .validation import validate_record


def make_record(state, proposed):
    """Render S/O from verbatim evidence; model supplies only assessments and future plans."""
    note = empty_record()
    initial = state.initial
    opening = initial.get('opening', '')
    note['S']['cc'] = str(opening)
    vitals = initial.get('vital_signs', '')
    if vitals:
        note['O']['exam'] = '시작 정보 활력징후: ' + (vitals if isinstance(vitals, str) else json.dumps(vitals, ensure_ascii=False))
    routed = set()
    for f in state.facts:
        source = next(e for e in state.evidence if e.id == f['evidence_id'])
        field = state.concepts[f['concept_id']]['field']
        if field == 'exam':
            continue  # O already renders the complete actual EXAM result below.
        item = f"[{f['id']}, 턴 {source.turn}, {f['subject']}, {f['temporality']}, {f['assertion']}] 질문: {source.question} / 환자 원문 전체: {source.response}"
        note['S'][field] += ('\n' if note['S'][field] else '')+item
        routed.add(source.id)
    unassigned = [f'(턴 {e.turn}) 질문: {e.question} / 환자: {e.response}' for e in state.evidence if e.action == 'SAY' and e.id not in routed]
    if unassigned:
        note['S']['hpi'] += ('\n' if note['S']['hpi'] else '')+'미분류 원문 대화:\n'+'\n'.join(unassigned)
    exams = [f'(턴 {e.turn}) {e.question}: {e.response}' for e in state.evidence if e.action == 'EXAM']
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
    differentials = proposed.get('differential', [])
    if isinstance(differentials, list):
        lines = []
        for d in differentials[:5]:
            if isinstance(d, dict) and isinstance(d.get('diagnosis'), str) and d['diagnosis'].strip():
                ids = d.get('evidence_ids', [])
                valid = [eid for eid in ids if isinstance(eid, str) and eid in sources] if isinstance(ids, list) else []
                lines.append('r/o '+d['diagnosis']+' (근거: '+(', '.join(valid) or '추가 확인 필요')+')')
        note['A']['differential'] = '\n'.join(lines)
    plan = proposed.get('plan', {})
    if isinstance(plan, dict):
        for k in note['P']:
            v = plan.get(k, '')
            if isinstance(v, str):
                note['P'][k] = v
    # Bound oversized provider responses without silently changing their meaning.
    for section in note.values():
        for key, text in section.items():
            raw = text.encode('utf-8')
            if len(raw) > 5900:
                section[key] = raw[:5800].decode('utf-8', errors='ignore')+'\n[분량 제한으로 원문 일부 생략; 전체는 실행 로그 참조]'
    validate_record(note, diagnosis)
    return note, diagnosis
