# NOVA 의료 agent 지식 DB

참고 의료 KB의 탐색 구성을 바탕으로 자체 구현한 지식 그래프 탐색기입니다. 촘촘한 개념 목록, 방향별 그래프, 연결 근거 테이블, 진료·구조·테이블 탭을 제공합니다. 밝은/어두운 테마와 모바일 목록 접기를 지원합니다.

## 실행

```bash
python3 -m meddb serve
# http://127.0.0.1:8765/#explore
python3 -m meddb validate
python3 -m meddb search 윌슨병
python3 -m meddb graph dismech-disease:Wilsons_Disease --include-draft
python3 -m meddb validate --version meddb-2026.10.10.4
```

Python 3.9 이상, 저장소 루트에서 실행합니다. 기본 서버·조회는 외부 패키지가 필요 없습니다. pip 패키지에는 데이터와 웹 자산이 포함되지 않습니다. 로컬 서버만 제공하며 환자 입력을 저장하지 않습니다.

## 현재 데이터

판: `meddb-2026.10.10.4`. 질병 3,339개, 소견 5,612개, 기전 23,631개, 관계 114,088개, 표준 용어 매핑 8,448개입니다.

- DisMech의 3,333개 YAML 항목을 commit `0cfe4bd579700d42c13d5fcc147e785e52c97966`에 고정해 수입했습니다. 질병→기전, 질병→표현형, 원본에서 명시한 기전 downstream 관계만 변환합니다. 동일 질병으로 명시한 소수의 기존 파일럿 개념을 합쳤고, 질병별 기전 ID는 출처 범위를 유지합니다.
- HPO 공식 `hp/releases/2026-09-01`에서 유효한 표현형 ID를 확인해 동일 ID의 소견을 공유합니다. 이름은 공식 용어로 정규화합니다. HPOA는 수입하지 않았습니다.
- DisMech가 제공한 MONDO 매핑은 출처 그대로 보존하고 별도 확인 완료로 표시하지 않습니다. KCD와 LOINC 및 검사 지식은 아직 없습니다.
- NIDDK 파일럿 9질병의 원문 근거 관계도 보존합니다. 모든 의학 관계와 의미 매핑은 로컬 의학 검수 전 초안입니다.
- 한국어 이름을 작성한 일부 개념에는 AI 번역 초안임을 기록합니다. 번역되지 않은 용어는 영어 원문을 표시합니다.

탐색 화면은 초안을 기본 표시하되 표시 상태를 알립니다. agent API·RDF export는 초안을 기본 제외합니다. 숫자가 커졌다고 의학적 타당성 검수가 완료된 것은 아닙니다. DisMech는 AI가 정리한 연구용 지식이며 원본의 검수와 우리 검수는 별도입니다. 원문 문헌 인용문은 복제하지 않고 근거 참조 ID 및 원문 파일 위치를 보존합니다. 빈도는 원본 분류 문자열만 보존하고 진단 확률로 변환하지 않습니다.

## 탐색 기능

- 검색 목록: 질병·소견·기전·검사, 한국어/영어/동의어/표준 코드, 연결 수·이름·코드 정렬. 상위 200개를 렌더링하고 전체 검색 가능.
- 방향 그래프: 출발→결과와 들어오는 관계→선택 개념을 분리. 단계·출처·초안 필터, 확대·축소·폭 맞춤·전체 보기. 노드 선택으로 상세 이동, 간선 선택으로 근거 행 강조, 이전 개념으로 복귀.
- 연결 근거: 들어오는/나가는 관계, 원본 위치·맥락·출처·문헌 링크. 그래프는 명시된 관계만 따라가며 표현형 연관을 인과로 바꾸지 않음.
- 진료: 검색 가능한 소견 입력, 있음·없음·미확인, 직접 표현형 공통점 후보와 근거. 미확인은 점수에 반영하지 않으며 부정은 확정 배제가 아님.
- 구조: 개념·주장·출처·표준 매핑의 구조 표시.
- 테이블: 전체 행 검색과 50행 페이지 처리.

## API와 agent

`GET /api/data`는 모든 초안을 포함한 압축 원본 탐색 스냅숏입니다. `GET /api/search?q=HP:0001945`, `GET /api/graph?node=nova:fever&direction=in&depth=2&draft=true&source=DisMech`, `POST /api/rank`.

순위 요청: `{"observations":{"nova:vomiting":"present"},"include_draft":true}`. 방향은 `in`/`out`/`both`. 결과에는 데이터 버전과 순위 산출의 근거가 포함됩니다. 원인 방향 탐색은 질병에서, 결과 방향 탐색은 소견·검사에서 멈춥니다. 파생질병은 깊이 한도 내에서 계속 탐색합니다. 이는 임상 인과추론이나 확률 모델이 아닙니다.

`KB(version="meddb-2026.10.10.4")`와 `KB.TOOLS`, `kb.call(name,args)`를 사용할 수 있습니다. 배포판은 `data/releases/`에 JSON 또는 JSON.gz로 보존하고 SHA256은 압축 전 파일 내용 기준입니다. 원본 탐색 스냅숏의 HTTP 응답은 gzip으로 전송합니다.

## 검증

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ontology.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m meddb validate-rdf --version meddb-2026.10.10.3 --include-draft
.venv/bin/python -m meddb validate-rdf --node dismech-disease:Wilsons_Disease --include-draft
```

22개 테스트: 초안 기본 제외, 미확인·부정 분리, 버전 재현, 방향 탐색, 출처 보존, RDF/SHACL, 잘못된 끝점·근거 누락·검수자 없는 승인 거부. 외부 패키지가 없는 기본 Python에서 SHACL 테스트는 skip됩니다.

전체 최신 JSON은 Python 구조 검증을 통과했습니다. 최신 RDF/SHACL은 윌슨병 결과 방향의 2단계 범위에서 2,424 triple을 검증했습니다(`docs/ontology-validation-expanded.json`). 이전 소규모 판은 전체 RDF 검증했습니다(`docs/ontology-validation.json`). 최신 11만 관계 전체에 대한 SHACL 실행이나 의학적 검수 완료를 의미하지 않습니다.

## 데이터 재수입

```bash
.venv/bin/python -m pip install PyYAML==6.0.3
.venv/bin/python tools/import_dismech.py /path/to/pinned/dismech /path/to/hp.obo --version meddb-YYYY.MM.DD.N
```

Importer는 로컬 고정 checkout만 읽고 YAML safe loader를 사용합니다. 새 판 이름은 --version으로 지정하며 이미 존재하는 판은 importer가 거부합니다. 원본 파일별 SHA256은 `data/terminology/dismech-manifest.json`에 기록했습니다.

이용 조건과 변환 내역: [THIRD_PARTY_NOTICES](docs/THIRD_PARTY_NOTICES.md). 디자인 참고: https://bbi-bbo.github.io/medagent-kb/ . 해당 팀의 코드·폰트·번들 데이터는 복사하지 않았습니다.

## KCD-9 로컬 조회

HIRA `배포용 상병마스터_260329.xlsx`에서 78,197개 명칭 행과 44,846개 고유 코드를 보존합니다. 활동분류도 포함하므로 코드 수는 질병 개념 수가 아닙니다. 원본과 추출본은 재배포 조건 확인 전까지 Git에서 제외했습니다.

```bash
# openpyxl을 사용할 수 있는 Python으로 실행
python tools/import_kcd.py /path/to/배포용\ 상병마스터_260329.xlsx data/terminology/kcd/hira-kcd9-260329.json.gz
python3 -m meddb serve
```

테이블 탭의 `KCD-9 상병마스터`에서 한영 명칭과 점 포함 코드로 검색할 수 있습니다. 구조 탭에 독립 컬렉션으로 표시합니다. 로컬 추출본이 없는 환경에서는 KCD API가 503을 반환하며 기존 그래프는 계속 작동합니다.

- `GET /api/kcd?q=윌슨&offset=0&limit=50`: 원문 명칭 행 검색·페이지 처리.
- `GET /api/kcd/code?code=E83.0`: 코드에 포함된 모든 명칭과 원문 위치.
- `GET /api/kcd/mappings?concept=dismech-disease:Wilsons_Disease`: 이름 일치에 따른 검수 전 매핑 후보. 승인된 매핑이나 질병 동등성 주장이 아닙니다.

KCD 접두어에서 계층을 임의 생성하지 않으며 청구 부가정보를 임상 배제 규칙으로 사용하지 않습니다. 현재 테스트는 25개입니다.


결과 그래프는 출발 질병 → 기전 1차/파생질병 → 기전 2차/파생질병 → … → 소견으로 배치합니다. 순환이 없는 부분은 표시된 간선의 가장 긴 경로로 단계를 결정하고, 순환 부분은 도달 단계로 배치합니다. 이는 임상적 시간 순서나 인과 검수 완료를 뜻하지 않습니다. 탐색 깊이는 도달 범위이고 화면 열은 그 안의 연결 경로 단계라 서로 다를 수 있습니다. 기본 탐색 깊이는 5이며 긴 그래프는 가로 스크롤하거나 폭 맞춤으로 볼 수 있습니다. 테스트는 26개입니다.

기전 사슬 화면은 질병의 직접 has_phenotype 연관을 아래 별도 목록에 보존합니다. 다른 명시 경로로 도달할 수 있는 중복 직통선은 화면에서만 숨기며 원본 주장과 근거 테이블은 유지합니다. 새 인과 관계를 생성하지 않습니다. 표시 로직 검증: `node tests/test_chain_graph.cjs`.
