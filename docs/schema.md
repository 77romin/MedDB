# 현재 지식 DB의 스키마

구조 화면은 실제 JSON 저장 구조를 논리 ERD로 보여줍니다. SQL 테이블이 설치되어 있는 것은 아닙니다. PK는 고유 식별자이며 FK는 다른 레코드 ID의 참조입니다. 현재 키와 관계 타입은 `meddb/kb.py`의 구조 검증에서 확인합니다.

| 구조 | 저장 위치 | 역할 |
|---|---|---|
| snapshot | JSON 최상위 객체 | 배포판의 version, format, scope와 컬렉션 |
| concepts | concepts[] | 질병·소견·기전을 kind로 구분하는 공통 개념 |
| sources | sources[] | 원본 URL, 버전, 접근일, 원본 해시 |
| assertions | assertions[] | 출발 개념, 관계 종류, 도착 개념, 출처, 원문 위치, 검수 상태 |
| mappings | concepts[].mappings[] | HPO·MONDO 등의 외부 용어 연결 |
| Disease / Finding / Mechanism | concepts의 kind 필터 | 독립 저장 테이블이 아닌 유형별 뷰 |

한 개념은 여러 관계의 출발점·도착점이 될 수 있습니다. 한 출처도 여러 관계·매핑에서 참조합니다. concepts.id ← assertions.subject/object, sources.id ← assertions.source_id/mappings.source_id가 핵심 참조입니다.

예를 들어 윌슨병과 간비대는 서로 다른 concepts 레코드입니다. assertions에 윌슨병을 subject, has_phenotype을 predicate, 간비대를 object로 저장합니다. 같은 레코드의 source_id는 DisMech 원문을 가리키고 locator는 phenotypes[0] 같은 원문 위치입니다. 간비대 개념의 mappings에는 HPO 용어와의 대응을 별도로 저장합니다.

현재 관계 타입:

- has_phenotype: Disease → Finding
- has_mechanism: Disease → Mechanism
- causes: Mechanism 또는 Exposure → Finding, Mechanism 또는 Disease
- supports_finding: Test → Finding

Test·Exposure·ClassificationCode 타입은 스키마에 있지만 현재 배포판에 해당 개념 레코드는 없습니다. 구조 화면의 행 수는 로딩한 데이터에서 계산합니다.

검수 상태는 draft/reviewed/rejected입니다. reviewed 관계와 매핑에는 검수자가 필요합니다. identifier_verified는 외부 ID와 이름을 확인했다는 뜻이며 임상적 동등성 검수와는 다릅니다. 숫자 frequency는 현재 null이고 원본 빈도 문자열은 frequency_label에 보존합니다.

조회 API는 assertions를 선택하고 출처·검수 상태를 필터링한 다음 subject/object의 개념을 붙여 그래프로 만듭니다. RDF export는 같은 데이터를 Concept·Assertion·Source·Mapping으로 변환하며, ontology/core.ttl과 ontology/shapes.ttl이 타입과 제약을 기술합니다.
