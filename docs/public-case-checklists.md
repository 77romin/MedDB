# 공개 증례 지식 점검표

평가 전용 자료입니다. 공개 정답·대본을 에이전트 실행 지식으로 가져오지 않습니다. 상태는 구조적 연결 여부이며 임상 검수 결과가 아닙니다.

## C01

맥락: {'age': 62, 'sex': 'female'}
원문: data/external/samples/nova-samples-2026/C01/model_record.json

| 영역 | 확인할 지식 | 현재 상태 | 원문 위치 |
|---|---|---|---|
| 문진 | 불면의 기간·양상과 약물 사용 관계 | no_direct_relation | S.hpi / A.differential |
| 문진 | 약 이름·회당 용량·복용 횟수·처방 출처 | draft_pathway | S.hpi / S.pmh |
| 감별 | 약의 효과 변화·감량 시 증상·감량 시도 | draft_pathway | A.evidence |
| 감별 | 일상 기능·안전·대인관계 영향 | draft_pathway | A.evidence |
| 안전 | 의식·호흡·급성 중독·심한 금단 위험 | draft_pathway | O.exam / P.disposition |
| 계획 | 갑작스러운 중단을 지시하지 않고 전문 진료 계획 확인 | draft_pathway | P.treatment / P.follow_up |

## C03

맥락: {'age': 6, 'sex': 'male', 'development_context': 'prepubertal child'}
원문: data/external/samples/nova-samples-2026/C03/model_record.json

| 영역 | 확인할 지식 | 현재 상태 | 원문 위치 |
|---|---|---|---|
| 관찰 | 정확한 키·체중과 연령별 성장도표 | draft_relation | A.evidence / P.tests |
| 문진 | 과거 계측치·성장속도·백분위 변화 | draft_pathway | S.hpi / A.evidence |
| 감별 | 부모 키와 가족의 성장·사춘기 시기 | draft_pathway | S.fh / A.differential |
| 감별 | 영양·만성질환·약물·발달·신체 비율 | draft_pathway | S.pmh / O.exam / A.differential |
| 안전 | 6세의 연령 적절한 사춘기 전 상태를 사춘기 지연으로 기록하지 않음 | draft_pathway | O.exam / A.evidence |
| 계획 | 골연령·원인 검사 계획과 연속 성장 추적 | draft_pathway | P.tests / P.follow_up |

## C10

맥락: {'age': 32, 'sex': 'female'}
원문: data/external/samples/nova-samples-2026/C10/model_record.json

| 영역 | 확인할 지식 | 현재 상태 | 원문 위치 |
|---|---|---|---|
| 문진 | 의도하지 않은 체중 감소 | draft_relation | S.hpi / A.evidence |
| 문진 | 식욕·식사량 변화 | draft_relation | S.hpi / A.evidence |
| 문진 | 더위 불내성 | draft_relation | S.hpi / A.evidence |
| 진찰 | 갑상선 비대의 형태와 압통 | draft_relation | O.exam / A.evidence |
| 진찰 | 안구·안검 소견 | draft_relation | O.exam / A.evidence |
| 감별 | 갑상선염·결절성 원인·외인성 원인과 구분 | draft_pathway | A.differential |
| 계획 | 갑상선 기능·항체 검사 계획과 긴급 평가 필요성 | draft_pathway | P.tests / P.disposition / P.follow_up |
