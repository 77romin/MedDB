# KCD와 주호소 스키마 도입 방향

확인일: 2026-10-10. 아래 내용은 도입 설계이며 현재 데이터에 추가된 레코드가 아닙니다.

## 역할

- KCD-9: 국내 질병 코드, 한영 명칭, 분류 계층, 포함·제외 조건을 버전과 함께 보존합니다. 국가데이터처 고시에 따르면 2026-01-01 시행입니다.
- MONDO/DisMech: 질병 개념과 병태생리 지식을 유지합니다. 코드와 질병 개념을 같은 ID로 합치지 않습니다.
- 주호소 스키마: 주호소 → 기전·분류 → 감별 질병으로 이어지는 교육적 구조를 원문 위치와 함께 보존합니다.

BBI-BBO README는 성균관의대 LRC PBL 주호소 스키마를 팀이 자체 수집했다고 설명합니다. 이 자료를 일반 공개 표준 또는 대학이 검수한 진단 지침으로 간주하지 않습니다. 원문 접근 및 활용·재배포 조건은 현재 확인하지 못했습니다.

## 제안 저장 구조

- classification_code: code_system, version, code, parent_code, label_ko, label_en, inclusions, exclusions, source_id.
- disease_code_mapping: concept_id, code_system, code_version, code, relation, method, source_id, review_status, reviewer. 하나의 코드에 여러 질병 개념이 대응할 수 있도록 별도 저장합니다.
- presentation: 주호소와 기존 Finding 개념의 연결.
- schema_doc: 문서, 출처, 원본 버전·해시.
- schema_node: doc_id, parent_id, ord, role, 원문 내용으로 교육자료의 트리를 보존.
- node_concept: schema_node에서 concepts로 대응시킨 결과와 검수 상태.

원문 트리 순서나 들여쓰기를 모두 인과 관계로 변환하지 않습니다. 주호소에서 감별 후보를 묶는 연결과 명시된 기전의 인과 관계를 구분합니다. 승인한 연결만 기존 assertions의 의학 관계로 사용합니다.

## 도입 순서

1. 공식 KCD-9/HIRA 상병마스터의 판과 이용 조건을 확인하고 원본 스냅숏을 고정합니다.
2. 코드 계층과 한영 명칭을 독립 컬렉션으로 수입합니다.
3. 기존 질병의 MONDO 매핑을 경유해 KCD 대응 후보를 생성하되 이름만 같다고 exact로 승인하지 않습니다.
4. 활용 가능한 주호소 원문을 확보해 문서 트리와 개념 대응을 수입합니다.
5. 검수 후 ERD·테이블·주호소 탐색과 agent API에 연결합니다.

출처:
- https://mods.go.kr/board.es?act=view&bid=246&list_no=437418&mid=a10301150000
- https://github.com/BBI-BBO/medagent-kb/blob/main/README.md
