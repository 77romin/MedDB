"""Conditional decision scopes, never observations or a mandatory action queue.

These prompts organize history-taking. They neither resolve a goal nor infer an
absence from a keyword. Only the Doctor can select an action using actual evidence.
Source rationale and applicability limitations: docs/CLINICAL_DECISION_AXES.md.
"""
import re


def decision_axes(state, clinical=None):
    clinical = clinical or {}
    # Use clinical responses/opening, excluding education replies. Questions are
    # deliberately excluded: asking about a medicine does not establish use.
    text = str(state.initial.get('opening', ''))+'\n'+'\n'.join(
        e.response for e in state.evidence if not e.communication)
    axes = []
    if re.search(r'수면제|졸피뎀|벤조|진정제|알프라졸람|로라제팜|디아제팜|졸피드', text, re.I):
        axes.append({'type':'medication_exposure', 'scope':[
            '약별 이름·함량·1회 개수·마지막 시각; 최근 24시간 낮 추가 복용과 평소 야간 사용을 구분',
            '처방약 외 간헐적 일반약·술·기타 진정제 병용; 다른 약 없다는 답의 범위 확인',
            '지금의 의식·호흡·보행/낙상 위험과 실제 관찰; 복용 목적과 직접 확인한 자해 의도 구분',
            '용량 변화·감량/거름의 반응·일상 손상·지원자; 현재 안전 평가와 이후 조절 계획 구분'],
            'not_equivalent':['야간 복용량 ≠ 최근 24시간 전체 노출','술 부인 ≠ 모든 병용약 부인','대답 가능 ≠ 호흡/보행 정상']})
    labels = ' '.join(h.get('label','') for h in clinical.get('hypotheses', []))
    if re.search(r'갑상[샘선].*항진|그레이브스|Graves', labels, re.I):
        scopes = ['확진 전 현재 빈맥·흉통·숨참의 발생 상황과 중증도; 필요한 심폐 관찰',
                  '눈 통증·시력/복시 등 실제 증상과 흡연; 눈 돌출 소견만으로 증상 범위 완료하지 않기',
                  '약물·보충제 노출과 과거/가족 갑상선 질환; 검사로 원인과 치료 적합성 확인']
        if clinical.get('sex') != 'M' and (clinical.get('age') is None or 12 <= clinical['age'] <= 55):
            scopes.append('치료 선택 전 임신 가능성/계획·수유 여부를 해당 환자에게 확인; 미확인은 음성이 아님')
        axes.append({'type':'thyroid_treatment_readiness', 'scope':scopes,
                     'not_equivalent':['진단 가설 ≠ 확진','가임 연령 ≠ 임신','운동 중 숨참 ≠ 안정 시 숨참 부인']})
    if (clinical.get('complaint') == 'short_stature' or re.search(r'저신장|성장|작은\s*키|키가\s*작', text)) and (clinical.get('age') is None or clinical['age'] < 19):
        axes.append({'type':'growth_trajectory', 'scope':[
            '본인의 연속 측정 시점·키·성장속도와 출생/만성질환/영양 맥락; 단일 키와 장기 경과 구분',
            '부모 각각의 성인 키, 어릴 때 키, 사춘기 시점 분리; 어린 시절 작은 부친을 성인 저신장으로 코딩하지 않기',
            '현재 성장 패턴에 맞는 잠정 원인·대안과 검사 결과 확인/장기 성장 재측정 목적·시점 분리'],
            'not_equivalent':['부친 어린 시절 작은 키 ≠ 성인 저신장','기록 존재 ≠ 실제 장기 성장 경과 확인']})
    return {'axes':axes, 'policy':'환자별 판단 참고입니다. 이미 답한 범위는 원문 ID로 대조하고 중요한 미확인 한 항목만 선택합니다. 이 목록의 존재는 소견·완료·강제 질문을 의미하지 않습니다.'} if axes else None
