# MedDB

N.O.V.A. 2026 대화형 의료 진단 AI 에이전트 대회용 **주호소 중심 진료 지식베이스**입니다 (팀 병명백백).

예선은 SAY·EXAM·DIAGNOSE로 진료하고 과정과 기록의 질로 채점하므로, 이 KB는 병명 사전이 아니라
**"무엇을 물어야 하고, 무엇이 아직 빠졌고, 언제 멈춰도 되는지"** 를 코드가 판단할 수 있게 하는 데 맞춰져 있습니다.

- 표준 라이브러리만 사용 (Python 3.12, 네트워크·모델 호출 없음)
- 원본은 사람이 고치는 JSON(`meddb/data/`), 실행 시에는 SQLite로 적재
- 질문 문장은 모두 30자 이하·물음표 하나, 진찰 문장은 동작 하나 — 검증기가 강제

## 지금 들어 있는 것 (v0.3.0)

| 항목 | 수 |
|---|---|
| 주호소 | 16 (흉통, 호흡곤란, 복통, 두통, 발열, 어지럼, 요통, 기침, 구토·설사, 배뇨 증상, 인후통, 두근거림, 근력 약화·마비, 실신, 의식 변화, 발진) |
| 질환 | 115 (그중 반드시 배제할 red flag 36) |
| 소견 (증상·병력·진찰 소견·활력징후) | 238 |
| 진찰 동작 | 41 |
| 자유 응답 문진 항목(슬롯) | 16 |
| 질환–소견 연결 | 960 (팀 작성 652, 팀 작성 + DDXPlus 일치 179, DDXPlus에서만 129) |
| 상병마스터 이름 | 47,640 (KCD 코드 21,299개) |
| 진료 통계 | KCD 3자리 × 성별 × 5세 연령군 환자수 |
| 진료지침 문서 연결 | 주호소 16개·질환 115개 모두, 문서 405개 (대회 제공 코퍼스의 서지 정보) |

외부 자료는 건강보험심사평가원 상병마스터·진료 통계(공공누리 제1유형)와 DDXPlus(CC BY 4.0)입니다.
질문 문장, 위험 질환 지정, 검사·처치 계획은 어느 자료에도 없어 팀이 직접 썼습니다.

> **임상 검수 전 초안입니다.** 팀이 쓴 내용은 [docs/SOURCES.md](docs/SOURCES.md)의 검수 절차를 거쳐야 합니다.
> KCD 코드는 상병마스터와 대조를 마쳤습니다 (검증기가 매번 확인).

## 빠른 시작

```bash
python -m meddb validate            # 원본 검증 (오류가 있으면 종료 코드 1)
python -m meddb demo "가슴이 너무 아파서 왔어요."
python -m meddb build               # dist/meddb.sqlite 생성 (선택)
python -m unittest discover -s tests
```

```python
from meddb import MedDB

db = MedDB.open()                                  # 패키지 안 원본을 메모리에 적재 (약 0.2초)
cid = db.match_complaint("58세 남자입니다. 가슴이 너무 아파서 왔어요.")[0]["id"]   # "chest_pain"
present = db.vital_flags({"BP": "150/90", "HR": 102, "RR": 20, "BT": 36.8, "SpO2": 96})

state = dict(present=present, absent=[], asked=[], exams_done=[], age=58, sex="M")
db.next_actions(cid, limit=3, **state)             # 다음 행동 후보 (SAY/EXAM 문장 포함)
db.candidates(cid, present, age=58, sex="M")       # 감별진단 후보
db.ready(cid, **state)                             # 진단해도 되는지 + 남은 필수 항목
db.plan("mi")                                      # SOAP의 P 재료와 설명용 SAY 문장
```

제출 ZIP에는 `meddb/` 폴더만 복사해 넣으면 됩니다 (약 1.3MB).
`python -m meddb build`로 만든 SQLite 파일(약 7MB)을 `MedDB.open("dist/meddb.sqlite")`로 열면 더 빨리 열립니다 (약 0.1초).

## API

상태는 호출하는 쪽이 들고, 함수는 상태를 인자로 받습니다.
`present`/`absent`는 확인된 소견 id, `asked`는 물어본 슬롯 id, `exams_done`은 시행한 진찰 id입니다.

| 함수 | 쓰는 곳 | 돌려주는 것 |
|---|---|---|
| `match_complaint(text)` | 환자 첫마디 → 주호소 | `[{id, ko, matched}]` |
| `vital_flags(vitals)` | 시작 시 활력징후 | 소견 id 목록 (성인 기준) |
| `vocabulary(complaint)` | LLM이 환자 답을 소견 id로 옮길 때 선택지 | `[{id, ko, kind}]` |
| `match_findings(text)` | 위 작업의 규칙 기반 보조 | `{present, absent}` (표현 사전 휴리스틱) |
| `next_actions(complaint, ...)` | 다음 행동 선택 | `[{type, text, stage, target, resolves, why}]` |
| `red_flags_pending(complaint, ...)` | 진단 전 안전 점검 | `[{id, ko, unchecked}]` |
| `candidates(complaint, present, absent, age, sex, k)` | 감별진단 | `[{id, ko, kcd, score, prior, share, matched, against, unknown_key}]` |
| `prior(disease, age, sex)` | 성·연령별 사전확률 점수 | −2 ~ 1.5, 통계가 없으면 `None` |
| `ready(complaint, ...)` | 진단 시점 판단 | `{ready, pending, top, margin}` |
| `plan(disease)` | SOAP P, 설명 SAY | `{test, treat, dispo, edu, explain, unsafe}` |
| `record(complaint, present, absent, answers, turns, vitals, exam_results)` | 공식 기록의 S·O 칸 초안 | `{S: {cc, hpi, pmh, fh, sh, ros}, O: {exam, tests}, A: {...}, P: {...}}` |
| `assessment_plan(complaint, disease, present, absent, turns, age, sex)` | 공식 기록의 A·P 칸 초안 | `{A: {diagnosis, evidence, differential}, P: {tests, treatment, disposition, follow_up, education}}` |
| `empty_note()` | 공식 칸을 모두 갖춘 빈 기록 | 위와 같은 구조, 값은 빈 문자열 |
| `describe(ids)`, `note_field(id)` | 항목이 기록의 어느 칸에 들어가는지 | `[{id, ko, kind, soap, sys, note}]`, `"S.ros"` 등 |
| `guidelines(id, lang, root)` | 주호소·질환의 대회 진료지침 문서 | `[{file, title, org, year, lang, type, license, path}]` |
| `read_guideline(path, max_chars)` | 지침 본문 읽기 (실행 환경) | 문자열 또는 `None` |
| `normalize_diagnosis(text)` | 진단명 → 질환·KCD (채점기) | 질환 dict. KB에 없으면 상병마스터에서 찾은 `{id: None, ko, kcd}`, 그래도 없으면 `None` |
| `kcd_lookup(text)` | 상병마스터 이름 → KCD 코드 | `{id: None, ko, kcd}` 또는 `None` |
| `disease(id)` | 질환 한 건 전체 | 소견별 출처(`sources`) 포함 |
| `rubric(complaint, disease)` | 자체 채점 기준 초안 | `{must_ask, must_exam, expected_plan, unsafe, ...}` |

`next_actions`의 단계(stage)와 순서:

1. `hpi` — 현병력 슬롯 (발생 시점, 양상, 악화 요인 등)
2. `red_flag` — 이 주호소에서 반드시 배제할 질환의 확인 소견
3. `core` — 주호소 필수 문진
4. `exam` — 주호소 필수 진찰
5. `discriminate` — 상위 후보를 가르는 소견 (1순위 비중이 0.6 이상이면 1순위의 미확인 핵심 소견만)
6. `background` — 과거력·약물·알레르기·가족력·흡연·음주

`discriminate`를 뺀 단계가 모두 비면 `ready`가 참이 됩니다. 필수 단계만 따라가면 주호소별로 14~22턴입니다.

`candidates`의 `score`는 소견 겹침 점수에 사전확률을 더한 값이고 `share`는 후보 사이의 상대 비중입니다. **확률이 아닙니다.**

사전확률(`prior`)은 건강보험 진료 통계에서 그 성·연령 칸의 전체 환자 중 해당 KCD 3자리가 차지하는 비중입니다.
3자리 단위라 같은 코드를 쓰는 질환(예: 대동맥 박리와 복부 대동맥류 파열)은 구분하지 못하고, 외래에서 오래 다니는 만성 질환이 높게 나옵니다.
그래서 가중치를 낮게 두고(0.5) 팀이 준 `freq`와 함께 씁니다.

## 초진 기록(SOAP)

`record`와 `assessment_plan`은 대회 문서의 기록 원칙에 맞춘 초안을 만듭니다.

- 넘겨받은 사실만 적습니다. 있음 `(+)`, 없음 `(-)`, 필수 항목인데 묻지 않은 것은 `( )`.
- 진찰은 받은 결과 문장을 그대로 적고 턴 번호를 붙입니다: `폐 청진: 양측 깨끗함 (턴 13)`.
- 감별진단에는 무엇이 없었고 무엇을 확인하지 못했는지 구분해 적습니다: `r/o 대동맥 박리 : 찢어지는 듯한 등 방사통 없음`.
- P는 KB의 계획(앞으로 할 일)입니다. 예선에는 검사가 없으므로 `O.tests`는 빈 문자열입니다.

칸 이름은 대회 문서를 따랐지만, **제출할 때의 정확한 자료 형태(중첩 여부 등)는 `nova_sdk.py`로 확인해야 합니다.**
A·P의 문장은 LLM이 다듬을 재료로 쓰는 것을 전제로 합니다.

## 진료지침 문서

대회가 실행 환경(`NOVA_GUIDELINES_DIR`)에 넣어 주는 진료지침 15,904개 중, 주호소·질환에 해당하는 문서를 목록의 제목으로 골라 연결했습니다.

```python
for doc in db.guidelines("chest_pain"):          # 앞쪽일수록 제목이 정확히 맞는 문서
    text = db.read_guideline(doc["path"], max_chars=4000) if doc["path"] else None
```

- KB에는 파일명·제목·발행기관·라이선스 같은 서지 정보만 있습니다. 본문은 실행 중에 읽습니다.
- 제목만 보고 골랐으므로 본문이 맞는지는 확인되지 않았습니다. 뒤쪽 문서일수록 빗나갈 수 있습니다.
- 연결된 문서의 대부분이 변경 금지 조건(CC BY-NC-ND, 공공누리 제4유형)입니다. 본문을 요약·번역해 저장소에 넣지 않습니다.

## 외부 자료 갱신

원본 파일은 저장소에 넣지 않습니다. 받아서 아래 도구로 `meddb/data/`의 가공 파일을 다시 만듭니다.

```bash
python tools/import_hira.py --kcd <상병마스터.csv> --stats <주부상병 3단 성별 연령군별 진료 통계.csv>
python tools/import_ddxplus.py --conditions release_conditions.json --evidences release_evidences.json
python tools/map_guidelines.py --catalog <진료지침 코퍼스의 catalog.csv>
```

진료지침 검색어와 제외어는 `tools/guideline_terms.json`에 있습니다.

DDXPlus 문진 항목과 KB 소견의 대응은 `tools/ddxplus_map.json`에 있습니다. 팀이 반대 소견으로 둔 연결과 충돌하면 팀 판단을 유지하고 도구가 충돌 목록을 출력합니다.

## 데이터 구조

자세한 필드는 [docs/SCHEMA.md](docs/SCHEMA.md).

```
주호소 ──슬롯·필수 문진·필수 진찰
   └──가능 질환 ──핵심(key)·보조(support)·반대(against) 소견
                 ├─배제 확인 소견(rule_out, red flag 질환)
                 └─계획(검사·치료·처치 결정·교육·설명 문장·금기)
소견 ──질문 문장(SAY) 또는 진찰 동작(EXAM), SOAP 위치, 환자 표현 사전
```

## 기여 방법

1. `main`에서 기능 브랜치를 만들고 `meddb/data/*.json`을 고칩니다.
2. `python -m meddb validate`와 `python -m unittest discover -s tests`가 통과해야 합니다.
3. 질환을 추가하면 대표 증례 하나를 `tests/test_meddb.py`의 `test_typical_presentations_rank_first`에 넣습니다.
4. 외부 자료를 참고했다면 `docs/SOURCES.md`에 출처와 라이선스를 먼저 적습니다.
5. PR을 올립니다.

## 알려진 한계

- 주호소 16개 밖의 내원 이유(관절통, 부종, 황달, 혈변, 질 출혈, 눈·귀 증상, 외상, 정신과 증상 등)는 아직 없습니다.
- 소아 증례는 다루지 않습니다. 활력징후 기준도 성인용입니다.
- DDXPlus는 호흡기·흉부 질환 49개 위주라 그 밖의 질환에는 외부 자료의 뒷받침이 없습니다.
- 사전확률은 KCD 3자리 단위의 진료 통계라 위에 적은 한계가 있습니다.
- `rubric`으로 자체 채점 기준을 만들 수는 있지만, **가상 증례를 이 KB로 만들면 점수가 부풀려집니다.** 증례는 다른 출처로 만듭니다.
