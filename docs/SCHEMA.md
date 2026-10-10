# 스키마

원본은 `meddb/data/`의 JSON 여섯 개이고, `meddb/build.py`가 검증한 뒤 아래 SQLite 표로 적재합니다.

## 원본 JSON

### `slots.json` — 자유 응답 문진 항목

있음/없음으로 답할 수 없는 항목입니다 (발생 시점, 통증 양상, 과거력 등). 점수 계산에는 쓰이지 않고 문진 완결성에만 쓰입니다.

| 필드 | 설명 |
|---|---|
| `id` | 영문 소문자·숫자·밑줄 |
| `ko` | 이름 |
| `soap` | SOAP 위치 (`S.현병력`, `S.과거력`, `S.약물`, `S.알레르기`, `S.가족력`) |
| `ask` | SAY 문장. 30자 이하, 물음표 하나로 끝남 |
| `sex`, `age` | 해당 성별·나이 범위에서만 묻는 항목 (선택). `age`는 `[최소, 최대]`, 한쪽은 `null` 가능 |

### `exams.json` — 진찰 동작

| 필드 | 설명 |
|---|---|
| `id` | `ex_`로 시작 |
| `ko` | 이름 |
| `action` | EXAM 문장. 동작 하나만 (병렬 표현 금지) |

### `findings.json` — 소견

| 필드 | 설명 |
|---|---|
| `id`, `ko` | |
| `kind` | `symptom` 증상 · `history` 병력·위험인자 · `sign` 진찰 소견 · `vital` 활력징후에서 도출 |
| `sys` | 계통 (전신, 심혈관, 호흡기, 소화기, 비뇨생식, 신경, 근골격, 이비인후, 눈, 피부, 정신, 내분비, 혈액) |
| `ask` | `symptom`·`history`의 SAY 문장 |
| `exam` | `sign`을 확인하는 진찰 id. 한 진찰이 여러 소견을 확인할 수 있음 |
| `alias` | 환자가 쓰는 표현 (부분 일치용, 선택) |
| `soap` | SOAP 위치를 기본값과 다르게 둘 때 (기본: 증상 `S.현병력`, 병력 `S.과거력`, 진찰 `O.진찰`, 활력 `O.활력징후`) |
| `sex`, `age` | 선택 |

### `diseases.json` — 질환

| 필드 | 설명 |
|---|---|
| `id`, `ko`, `en` | |
| `kcd` | KCD 코드. 맞는 코드가 없으면 `null` |
| `urgency` | `emergent` · `urgent` · `routine` |
| `red_flag` | 해당 주호소에서 반드시 배제해야 하는 질환인지 |
| `freq` | 내원 환자 중 흔한 정도 1~3 |
| `sex`, `age` | 선택. 성별이 다르면 후보에서 빠지고, 나이가 벗어나면 감점 |
| `alias` | 진단명 다른 표기 |
| `key` | 핵심 소견 (있으면 +3, 없으면 −1.5). 2개 이상 |
| `support` | 보조 소견 (있으면 +1, 없으면 −0.3) |
| `against` | 있으면 가능성이 낮아지는 소견 (−2) |
| `rule_out` | 진단 전에 있음/없음을 확인해야 하는 소견. `key`·`support` 안에서 고르며 red flag 질환은 필수 |
| `dispo` | 처치 결정 (응급·입원·외래) |
| `plan.test` | 검사 계획 |
| `plan.treat` | 치료·처치 |
| `plan.edu` | 교육·추적 (SOAP P에 기록) |
| `plan.explain` | 진단 전에 SAY로 할 설명 문장. 30자 이하 |
| `plan.unsafe` | 하면 안 되는 처치 (안전 점검·채점용) |

### `complaints.json` — 주호소

| 필드 | 설명 |
|---|---|
| `id`, `ko` | |
| `alias` | 환자 첫마디 표현. 띄어 쓴 어절 사이에 3글자까지 끼어도 맞음 |
| `slots` | 현병력 슬롯 (순서대로) |
| `ask` | 항상 확인하는 소견 |
| `exams` | 항상 하는 진찰 |
| `diseases` | 감별진단 범위 |

### `common.json`

- `background` — 모든 주호소에서 확인하는 과거력·사회력 항목
- `vital_rules` — 활력징후 → 소견 규칙 (성인 기준)
- `phrases` — 공감·마무리 문장 (30자 이하)
- `meta` — 판, 검수 상태

## SQLite 표

| 표 | 내용 |
|---|---|
| `slot`, `exam`, `finding`, `disease`, `complaint` | 위 항목 |
| `disease_finding(disease_id, finding_id, role, rule_out)` | 질환–소견 연결 |
| `disease_plan(disease_id, kind, seq, text)` | 계획 |
| `complaint_item(complaint_id, kind, ref_id, seq)` | 주호소의 슬롯·소견·진찰 |
| `complaint_disease(complaint_id, disease_id, seq)` | 주호소–질환 |
| `background_item(kind, ref_id, seq)` | 공통 병력 항목 |
| `alias(kind, ref_id, text)` | 표현 사전 |
| `vital_rule`, `phrase`, `meta` | |

## 검증 규칙

`python -m meddb validate`가 확인하는 것:

- id 형식·중복, 모든 참조가 실제로 존재하는지
- SAY 문장: 30자 이하, 물음표 하나로 끝남
- EXAM 문장: 병렬 표현(`그리고`, `및`, 쉼표 등) 없음
- 지시문처럼 읽힐 수 있는 표현 없음 (프롬프트 인젝션으로 오해받지 않도록)
- 질환: 핵심 소견 2개 이상, 계획 항목 채워짐, red flag면 `rule_out` 있음
- 쓰이지 않는 소견·질환·진찰은 경고
