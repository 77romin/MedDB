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
    routed = set()
    rendered_sources = set()
    for f in state.facts:
        source = next(e for e in state.evidence if e.id == f['evidence_id'])
        field = state.concepts[f['concept_id']]['field']
        if field == 'exam':
            continue  # O already renders the complete actual EXAM result below.
        key = (field,source.id)
        if key in rendered_sources:
            note['S'][field] += '\n추가 모델 추출: '+json.dumps({k:f[k] for k in ('id','concept_id','assertion','attribute','value','unit','time_anchor') if k in f},ensure_ascii=False)
            continue
        rendered_sources.add(key)
        item = f"[{f['id']}, {source.id}, 턴 {source.turn}, {f['subject']}, {f['temporality']}, {f['assertion']}] 질문: {source.question} / 환자 원문 전체: {source.response}"
        if f.get('attribute'):
            item += ' / 출처 검증 관찰: '+json.dumps({k:f[k] for k in ('attribute','value','unit','time_anchor') if k in f},ensure_ascii=False)
        note['S'][field] += ('\n' if note['S'][field] else '')+item
        routed.add(source.id)
    explanations = {e.id for e in state.delivered_explanations()}
    unassigned = [f'[{e.id}, 턴 {e.turn}] 질문: {e.question} / 환자: {e.response}' for e in state.evidence
                  if e.action == 'SAY' and e.id not in routed and e.id not in explanations]
    additional = [f'[{e.id}, 턴 {e.turn}] 설명 중 환자 추가 응답: {e.response}' for e in state.evidence
                  if e.id in explanations and e.id not in routed and e.response.strip(' .!。') not in {'네','예','알겠습니다','네, 알겠습니다','감사합니다'}]
    unassigned += additional
    if unassigned:
        note['S']['hpi'] += ('\n' if note['S']['hpi'] else '')+'미분류 원문 대화:\n'+'\n'.join(unassigned)
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
    differentials = proposed.get('differential', [])
    if isinstance(differentials, list):
        lines = []
        for d in differentials[:5]:
            if isinstance(d, dict) and isinstance(d.get('diagnosis'), str) and d['diagnosis'].strip():
                ids = d.get('evidence_ids', [])
                valid = [eid for eid in ids if isinstance(eid, str) and eid in sources] if isinstance(ids, list) else []
                lines.append('r/o '+d['diagnosis']+' (근거: '+(', '.join(valid) or '추가 확인 필요')+')')
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
