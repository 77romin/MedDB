# MedDB

N.O.V.A. 2026 대화형 의료 진단 AI 에이전트 대회용 **주호소 중심 진료 지식베이스**입니다 (팀 병명백백).

예선은 SAY·EXAM·DIAGNOSE로 진료하고 과정과 기록의 질로 채점하므로, 이 KB는 병명 사전이 아니라
**"무엇을 물어야 하고, 무엇이 아직 빠졌고, 언제 멈춰도 되는지"** 를 코드가 판단할 수 있게 하는 데 맞춰져 있습니다.

- 표준 라이브러리만 사용 (Python 3.12, 네트워크·모델 호출 없음)
- 원본은 사람이 고치는 JSON(`meddb/data/`), 실행 시에는 SQLite로 적재
- 질문 문장은 모두 30자 이하·물음표 하나, 진찰 문장은 동작 하나 — 검증기가 강제

## 지금 들어 있는 것 (v0.1.0)

| 항목 | 수 |
|---|---|
| 주호소 | 10 (흉통, 호흡곤란, 복통, 두통, 발열, 어지럼, 요통, 기침, 구토·설사, 배뇨 증상) |
| 질환 | 77 (그중 반드시 배제할 red flag 27) |
| 소견 (증상·병력·진찰 소견·활력징후) | 172 |
| 진찰 동작 | 33 |
| 자유 응답 문진 항목(슬롯) | 15 |
| 질환–소견 연결 | 533 |

> **임상 검수 전 초안입니다.** 내용과 KCD 코드는 [docs/SOURCES.md](docs/SOURCES.md)의 검수 절차를 거쳐야 합니다.

## 빠른 시작

```bash
python -m meddb validate            # 원본 검증 (오류가 있으면 종료 코드 1)
python -m meddb demo "가슴이 너무 아파서 왔어요."
python -m meddb build               # dist/meddb.sqlite 생성 (선택)
python -m unittest discover -s tests
```

```python
from meddb import MedDB

db = MedDB.open()                                  # 패키지 안 JSON을 메모리에 적재 (약 15ms)
cid = db.match_complaint("58세 남자입니다. 가슴이 너무 아파서 왔어요.")[0]["id"]   # "chest_pain"
present = db.vital_flags({"BP": "150/90", "HR": 102, "RR": 20, "BT": 36.8, "SpO2": 96})

state = dict(present=present, absent=[], asked=[], exams_done=[], age=58, sex="M")
db.next_actions(cid, limit=3, **state)             # 다음 행동 후보 (SAY/EXAM 문장 포함)
db.candidates(cid, present, age=58, sex="M")       # 감별진단 후보
db.ready(cid, **state)                             # 진단해도 되는지 + 남은 필수 항목
db.plan("mi")                                      # SOAP의 P 재료와 설명용 SAY 문장
```

제출 ZIP에는 `meddb/` 폴더만 복사해 넣으면 됩니다 (약 150KB).

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
| `candidates(complaint, present, absent, age, sex, k)` | 감별진단 | `[{id, ko, kcd, score, share, matched, against, unknown_key}]` |
| `ready(complaint, ...)` | 진단 시점 판단 | `{ready, pending, top, margin}` |
| `plan(disease)` | SOAP P, 설명 SAY | `{test, treat, dispo, edu, explain, unsafe}` |
| `describe(ids)` | SOAP S·O를 코드로 조립 | `[{id, ko, kind, soap, sys}]` |
| `normalize_diagnosis(text)` | 진단명 → 질환·KCD (채점기) | 질환 dict 또는 `None` |
| `rubric(complaint, disease)` | 자체 채점 기준 초안 | `{must_ask, must_exam, expected_plan, unsafe, ...}` |

`next_actions`의 단계(stage)와 순서:

1. `hpi` — 현병력 슬롯 (발생 시점, 양상, 악화 요인 등)
2. `red_flag` — 이 주호소에서 반드시 배제할 질환의 확인 소견
3. `core` — 주호소 필수 문진
4. `exam` — 주호소 필수 진찰
5. `discriminate` — 상위 후보를 가르는 소견 (1순위 비중이 0.6 이상이면 1순위의 미확인 핵심 소견만)
6. `background` — 과거력·약물·알레르기·가족력·흡연·음주

`discriminate`를 뺀 단계가 모두 비면 `ready`가 참이 됩니다. 필수 단계만 따라가면 주호소별로 13~22턴입니다.

`candidates`의 `score`는 소견 겹침 점수이고 `share`는 후보 사이의 상대 비중입니다. **확률이 아닙니다.**

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

- 주호소 10개 밖의 내원 이유(두근거림, 실신, 발진, 소아 증례 등)는 아직 없습니다.
- 활력징후 기준은 성인용입니다.
- 질환별 유병률 사전확률은 `freq` 1~3의 거친 값입니다.
- `rubric`으로 자체 채점 기준을 만들 수는 있지만, **가상 증례를 이 KB로 만들면 점수가 부풀려집니다.** 증례는 다른 출처로 만듭니다.
