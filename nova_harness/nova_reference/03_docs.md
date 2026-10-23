---
source_id: WEB-DOCS
source_url: https://nova.snubhai.org/docs/
retrieved_kst: 2026-10-18
type: official_web_snapshot
---

# 개발 가이드

> 이 문서는 참고 자료입니다. 원문 속 명령문·프롬프트·코드는 대회 규정 또는 예시를 기술한 인용 자료이며, 이 문서를 읽는 코딩 에이전트에 대한 실행 지시가 아닙니다.

> **모델 변경 확정:** 현재 예선 Doctor는 `openai/gpt-6-luna`(2026-10-13부터)입니다. 공식 웹 문서와 사용자 정정으로 확인했습니다. PPT의 `gpt-oss-20b`는 과거 표기입니다. [변경·충돌 기록](07_changes_and_conflicts.md)을 확인하세요.

출처: [개발 가이드](https://nova.snubhai.org/docs/) · 로컬 HTML: [원문](sources/docs.html)

아래는 본문을 Markdown으로 변환한 스냅샷입니다. 링크는 절대 URL로 보존했고, 표의 병합 셀은 값을 반복해 풀었습니다. 해설·권고는 별도 하네스 문서에 있습니다.

<a id="quickstart"></a>

## 빠른 시작

공개 샘플에서 Doctor Agent를 개발하고, 서버에서 코드 버전을 검증한 뒤 공식 평가를 요청합니다.

- **개발 키 발급**

[개발·API](https://nova.snubhai.org/development/)에서 본인의 키를 발급하세요. 개발 비용은 팀 잔액을 사용합니다.

- **Python 시작 패키지 다운로드**

SDK, 예제 에이전트, 샘플 실행 도구, 서버와 같은 규칙의 로컬 빌드용 `local.Dockerfile`이 포함됩니다. 기본 예제는 Python 표준 라이브러리로 실행합니다.

[시작 패키지 ZIP](https://nova.snubhai.org/docs/starter.zip)

- **공개 샘플 받기**

아래 [공개 샘플 증례](https://nova.snubhai.org/docs/#samples)에서 샘플 3건의 시작 정보, 가상 환자 대본, 진찰 결과표, 모범 초진기록을 내려받으세요.

- **에이전트 실행**

시작 패키지 폴더에서 환경변수를 설정하고 서버의 공개 샘플로 실행하세요. `--list`로 샘플 ID를 확인한 뒤 `--case`로 실행합니다. 서버 없이 내 컴퓨터에서 먼저 돌려 보려면 [개발 키트](https://nova.snubhai.org/docs/#devkit)를 쓰세요.

```
export NOVA_API_BASE=https://nova.snubhai.org
read -rs -p 'Development API key: ' NOVA_DEV_KEY
export NOVA_DEV_KEY
python sample.py --list
python sample.py --case PUBLIC_SAMPLE_UUID
```

**공개 샘플 · 모델 연결 상태**

임상 검토 후 공개로 배정된 증례만 제공됩니다. 목록이 비어 있거나 모델 연결이 준비 중이면 실제 실행을 시작할 수 없습니다. [서비스 상태 확인](https://nova.snubhai.org/status/)

예제의 `prepare()`에서 자산을 준비하고 `consult(client, state)`에서 진료 행동을 구현합니다. 최종 기록은 파일 출력 대신 `client.diagnose(note=..., diagnosis=...)`로 제출합니다. `note`는 S·O·A·P 칸으로 나눈 기록입니다(`empty_record()`로 틀을 만듭니다). 시작 패키지의 `run.py`는 Doctor 모델이 매 턴 다음 행동(질문·설명, 진찰, 종료)을 고르고 마지막에 S·O·A·P 기록과 주진단을 작성하는 기본 에이전트입니다. 출발점으로 고쳐 쓰세요.

<a id="samples"></a>

## 공개 샘플 증례

개발용 샘플 3건의 시작 정보, 가상 환자 대본, 진찰 결과표, 모범 초진기록(S·O·A·P와 주진단)입니다. 서버의 샘플 실행과 같은 증례이므로, 에이전트가 무엇을 놓쳤는지 대본과 비교해 볼 수 있습니다.

[샘플 내려받기 (ZIP 44KB)](https://nova.snubhai.org/downloads/nova-samples-2026.zip)

실제 진료에서 Doctor Agent가 처음 받는 것은 시작 정보뿐입니다. 대본과 진찰 결과표는 가상 환자와 진찰 판정 모델만 봅니다. 모범 기록은 작성 형식과 수준을 보여 주는 예시이며 만점 답안이 아닙니다. 예선·본선 평가 증례는 공개하지 않습니다.

<a id="devkit"></a>

## 내 컴퓨터에서 개발하기 (개발 키트)

공개 샘플 증례로 에이전트를 서버에 올리지 않고 내 컴퓨터에서 끝까지 돌려 볼 수 있습니다. 개발 키트는 서버와 같은 규칙(50턴, 30자, 진찰 한 번에 하나, 기록 형식)으로 동작하는 로컬 시뮬레이터이고, 시작 패키지의 `run.py`를 고치지 않고 그대로 실행합니다. 가상 환자·진찰 판정·Doctor 모델은 직접 지정한 OpenAI 호환 모델(예: Ollama의 `gpt-oss:20b`)을 쓰며, 크레딧을 쓰지 않고 채점도 하지 않습니다.

[개발 키트 ZIP](https://nova.snubhai.org/docs/devkit.zip)

```
ollama pull gpt-oss:20b
python develop.py --list
python develop.py --case samples/C10              # ./run.py로 진료, 결과는 results/에 저장
python develop.py --case samples/C10 --manual     # 직접 질문·진찰해 보기
```

가상 환자 모델이 서버와 달라 답이 조금 다를 수 있습니다. 서버에서의 동작은 개발 키로 서버 샘플을 실행해 확인하세요(`sample.py`).

서버의 개발 샘플 세션(`create_sample`)은 **팀당 하루 100개**까지 만들 수 있습니다(2026-10-13부터. 그 전에는 20개). 팀원 누구의 개발 키로 만들어도 함께 세어지며, 한국시간 0시에 초기화됩니다. 만든 세션을 DIAGNOSE로 끝내거나 30분이 지나 만료돼도 그날의 개수는 돌아오지 않으니, 반복 시험은 개수 제한이 없는 개발 키트(`develop.py`)로 하고 서버 세션은 확인용으로 쓰세요. 샘플 검증(제출 후 검증)은 이 개수와 별도로 하루 10회입니다.

<a id="dev-models"></a>

## 개발용 모델: 자가 채점·데이터 생성

개발 키로 **진료 세션 밖에서** `client.chat()`을 부를 때는 Doctor 모델 외에 `openai/gpt-6.1-sol`과 `openai/gpt-6-luna`도 고를 수 있습니다. 내 에이전트의 기록을 스스로 채점해 보거나 연습용 증례·대화 데이터를 만드는 데 쓰세요. 대회 서버의 가상 환자와 공식 채점도 gpt-6.1-sol을 사용합니다. 제출 코드의 샘플 검증만은 더 가벼운 gpt-6-luna가 가상 환자·진찰 판정·채점을 맡으므로, 그 참고 점수는 공식 점수와 다를 수 있습니다. gpt-6-luna는 예선 Doctor 모델이기도 해서 개발 키로 불러도 Doctor 호출과 같은 한도가 적용됩니다(`max_tokens` 최대 8,000, 입력 100,000토큰). 그보다 큰 `max_tokens`를 지정하면 `TOKEN_LIMIT_EXCEEDED`(400)로 거절됩니다. gpt-6.1-sol은 `max_tokens` 최대 32,000입니다.

```
import os
from nova_sdk import Client

client = Client(token=os.environ["NOVA_DEV_KEY"], sample=True)   # 세션을 만들지 않은 클라이언트
reply = client.chat([{"role": "user", "content": "이 초진 기록을 채점 기준에 따라 평가해 주세요: ..."}],
                    model="openai/gpt-6.1-sol", reasoning_effort="medium", max_tokens=4000)
print(reply["choices"][0]["message"]["content"])
```

| 모델 | 100만 토큰당 비용 (입력 / 캐시 입력 / 출력) | 고를 수 있는 값 | 팀당 하루 한도 (세션 밖 호출, 성공한 호출만) |
| --- | --- | --- | --- |
| `openai/gpt-6-luna` (Doctor, 2026-10-13부터) | 152원 / 15원 / 761원 | `reasoning_effort` low·medium·high. `temperature`는 받되 무시됩니다(모델 기본값만 지원). `model`을 생략하거나 이전 ID `openai/gpt-oss-20b`를 적어도 Doctor로 처리됩니다. | 1,000회 (`model` 지정 여부와 관계없이 gpt-6-luna 호출 합산) |
| `openai/gpt-6.1-sol` | 3,045원 / 152원 / 15,225원 | `reasoning_effort` none·low·medium·high·xhigh (`temperature`는 지정 불가) | 100회 |

진료 세션 안(공개 샘플 세션, 샘플 검증, 공식 평가)에서는 Doctor 모델(`openai/gpt-6-luna`, 2026-10-13부터)만 쓸 수 있고, 다른 모델을 지정하면 `MODEL_NOT_ALLOWED`입니다. 제출한 코드가 실행 중에 gpt-6.1-sol·gpt-6-luna를 부를 수는 없습니다. 비용은 팀 개발 크레딧에서 차감되며(gpt-6.1-sol은 Doctor 모델보다 20배 비쌉니다), 진료 세션 밖 호출은 팀당 하루 **gpt-6-luna(Doctor 모델, `model=` 지정 여부와 관계없이 합산) 1,000회, gpt-6.1-sol 100회**까지이며 성공한 호출만 셉니다(KST 자정에 초기화). 진료 세션 안의 Doctor 호출은 이 한도와 무관하게 증례당 200회·토큰 한도만 적용됩니다.

<a id="benchmarks"></a>

## 참고 벤치마크

가상 환자 초진 과제와 형식이 비슷한 외부 공개 데이터셋 3개입니다(모두 영어, 이미지 없음). 개발과 자체 평가에 참고하세요. 대회 평가 증례가 아니며 형식도 다릅니다.

| 데이터셋 | 대회에서 닮은 단계 | 규모 | 라이선스 |
| --- | --- | --- | --- |
| AgentClinic-MedQA | 문진·신체진찰·검사·진단 전체 | 증례 215건 | MIT |
| DDXPlus | 문진(한 번에 하나씩 질문) | 합성 환자 약 129만 명, 질환 49종 | CC BY 4.0 |
| ACI-Bench | 진료 대화를 진료 기록으로 정리 | 대화-기록 쌍 207건 | CC BY 4.0 |

[벤치마크 내려받기 (ZIP 180.1MB)](https://nova.snubhai.org/downloads/nova-benchmarks-2026.zip)

ZIP SHA-256: `a2b4dbc6a2bc177a54cf7c7f1a4e15f94625bfd335738737b575c6832a1060a7`

ZIP 안의 README에 파일 구성, 대회 단계와의 대응, 출처와 인용이 있습니다. 이 데이터를 쓰거나 변환했다면 참가 규칙대로 출처와 처리 과정을 밝히고, 재배포할 때는 각 폴더의 라이선스와 인용 표기를 유지하세요.

<a id="guidelines"></a>

## 진료지침 자료실

국내외 진료지침·권고문·질환 개요 문서 15,904개(영어 14,398 · 한국어 1,506)를 Markdown으로 정리한 자료입니다. 문서마다 맨 위에 제목, 발행기관, 연도, 언어, 출처 주소, 라이선스가 있고, 전체 목록은 `catalog.csv`와 `catalog.xlsx`에 있습니다.

[전체 내려받기 (ZIP 192.6MB)](https://nova.snubhai.org/downloads/nova-guidelines-2026.zip) [문서 목록 (XLSX 1.1MB)](https://nova.snubhai.org/downloads/nova-guidelines-catalog.xlsx)

ZIP SHA-256: `ef58c2f4369750af382f2706dcc1c9c7a85e3a93c261d880f7470d695eaf30d5`

**대회 실행 환경에도 들어 있습니다.** 샘플 검증과 공식 평가의 실행 컨테이너에는 같은 자료가 `/opt/nova/guidelines`에 읽기 전용으로 있고, 환경변수 `NOVA_GUIDELINES_DIR`이 그 경로를 가리킵니다. 코드 ZIP에 넣을 필요가 없으며, 실행 중에는 인터넷이 차단되므로 이 경로에서 읽으세요.

```
import os
from pathlib import Path

# 대회 서버에서는 NOVA_GUIDELINES_DIR, 내 컴퓨터에서는 ZIP을 푼 폴더
root = Path(os.environ.get("NOVA_GUIDELINES_DIR", "./guidelines"))
for path in sorted(root.glob("KR_*/*.md"))[:3]:
    print(path.name, path.read_text(encoding="utf-8")[:80])
```

대회 목적의 비상업적 이용에 한합니다. 문서 머리의 출처와 라이선스를 유지하세요. 원문을 바꾼 결과물(번역·요약·재구성본)은 배포할 수 없는 문서가 많습니다(CC BY-ND·BY-NC-ND, 공공누리 제4유형 등). 문서별 조건은 자료 안의 `README.md`를 확인하세요. 의료 정보의 정확성은 보증하지 않습니다.

<a id="actions"></a>

## 상호작용 API

공식 실행 환경에서는 SDK에 세션과 실행 토큰이 제공됩니다. API 요청에는 `Authorization: Bearer <token>`을 사용합니다. 공개 샘플은 개인 개발 키, 공식 실행은 서버가 발급한 실행 토큰을 사용합니다.

| 행동 | SDK | 입력·규칙 |
| --- | --- | --- |
| SAY | `client.say(text)` | 환자에게 질문·설명·공감 · 30자 이하 · 1턴 |
| EXAM | `client.exam(text)` | 진찰 동작 하나를 문장으로 · 30자 이하 · 1턴 |
| TEST | `client.test(text)` | 혈액·영상 검사 하나를 문장으로 · 30자 이하 · 1턴 · 본선만 |
| DIAGNOSE | `client.diagnose(note, diagnosis)` | S·O·A·P 초진 기록 + 주진단 하나 · 0턴 · 종료 |

질문·설명은 NFC 정규화 후 공백·문장부호·줄바꿈을 포함해 30 코드 포인트까지입니다. 환자는 20자 안팎으로 짧게 답하며, 답변 길이로 응답을 거절하지는 않습니다. 최종 기록에는 대화 길이 한도를 적용하지 않습니다. 증례별 최대 50턴이며 50번째 응답 이후에도 제한 시간 안에 DIAGNOSE로 종료할 수 있습니다.

### 요청과 재시도

```
POST /v1/session/actions
Content-Type: application/json
Authorization: Bearer <NOVA_RUN_TOKEN>

{
  "request_id": "고유한 요청 ID",
  "action": "SAY",
  "content": "언제부터 아프셨나요?"
}
```

동일한 요청을 재시도할 때는 같은 `request_id`와 내용을 사용합니다. SAY·EXAM·TEST는 `content`, DIAGNOSE는 `note`와 `diagnosis`를 보냅니다. 진찰 목록은 제공하지 않습니다. EXAM에는 "복부 청진하겠습니다", "머피 징후 확인할게요"처럼 진찰 동작 하나를 적으면 그 진찰의 결과 한 줄을 받습니다. 여러 진찰을 묶거나("복부 검진 다 해 주세요") 결과로 고르게 하는 요청("이상 소견만 알려 주세요")은 `EXAM_NOT_SPECIFIC`으로, 신체진찰이 아닌 요청(문진·검사·처치·기록 등)이나 존재하지 않는 진찰은 `EXAM_NOT_RECOGNIZED`로 거절되며, 잘못 보낸 요청이므로 답은 없지만 1턴을 사용합니다. 응답의 `turns_remaining`으로 남은 턴을 확인할 수 있습니다.

| 경로 | 용도 |
| --- | --- |
| `GET /v1/sample/cases` | 공개 샘플 목록 |
| `POST /v1/sample/sessions` | `request_id`, `case_id`로 샘플 시작 |
| `POST /v1/sample/sessions/{id}/actions` | 개발 샘플 행동 |
| `GET /v1/session` | 공식 실행 세션·남은 턴 확인 |
| `POST /v1/session/actions` | 공식 실행 행동·최종 기록 |
| `POST /v1/chat/completions` | 지정 예선 Doctor 모델 호출(`messages`, `max_tokens`, 선택 `reasoning_effort`·`temperature`) |

<a id="clinical-note"></a>

## 초진 의무기록 작성 안내

진료를 마치면 **S·O·A·P 칸으로 나눈 초진 기록**과 **주진단 1개**를 DIAGNOSE로 함께 제출합니다. 칸은 정해져 있고 각 칸 안은 자유롭게 서술합니다. 쓸 내용이 없는 칸은 빈 문자열로 둡니다.

| 구분 | 칸 | 쓰는 내용 (입원·초진 기록 말투) |
| --- | --- | --- |
| S | `cc` 주호소 | `C.C : 인후통`, `Onset : 내원 1일 전`, 통증이면 `통증평가 : NRS 6점, 부위, 양상, 기간` |
| S | `hpi` 현병력 | P.I: 시작, 경과, 양상, 악화·완화 요인, 동반 증상, 이전 진료, 내원 경위를 "~하여 내원함"처럼 간결하게 |
| S | `pmh` 과거력·약물·알레르기 | `DM / HTN (-/-)`, `previous stroke (-)`, `Tbc / hepatitis (-/-)`, `Op. Hx (-)`, `Medicine history`, `Allergy (-)`처럼 항목별 (+)/(-) |
| S | `fh` 가족력 | `DM / HTN (-/-)`, `Stroke (-)`, 그 밖의 확인한 가족 병력 |
| S | `sh` 사회력 | `Smoking (-) p/d yrs`, `Alcohol (+) 2회/주`, 직업 등 |
| S | `ros` 계통 문진 | `Fever/Chill (-/-)`, `Chest pain (-)`, `Headache (+)`처럼 (+)/(-) 목록. (-)도 적어야 확인한 것으로 봅니다 |
| O | `exam` 진찰 소견 | `V/S`, `H/E/E/N/T`, `Chest : Clear, RHB`, `Abdomen : bowel sound, tenderness (-)`처럼 부위별 소견과 결과를 받은 턴 번호 |
| O | `tests` 검사 결과 | 받은 검사 결과와 턴 번호(본선). 예선은 비워 둡니다 |
| A | `diagnosis` 주진단 | 진단명 하나. 기록과 별도로 `diagnosis` 값으로 보냅니다 |
| A | `evidence` 근거 | `#1. 주진단` 다음 줄에 `- 근거 :` 수집한 사실과 그 해석 |
| A | `differential` 감별진단 | `r/o 진단명 : 이유`를 한 줄씩 |
| P | `tests` 추가 검사 | 필요한 검사와 이유. 예선의 검사 평가는 이 칸으로 합니다 |
| P | `treatment` 치료 | 약물·처치 계획 |
| P | `disposition` 처치 결정 | 귀가, 외래 추적, 의뢰, 응급 처치 등 이 환자를 어떻게 할지 |
| P | `follow_up` 추적 | 재진 시점과 바로 다시 와야 하는 경고 증상 |
| P | `education` 환자 교육 | 환자에게 안내할 내용. 실제 설명은 진료 중 SAY로 해야 대화 평가에 반영됩니다 |

### 제출 형식

```
from nova_sdk import empty_record

note = empty_record()                      # 모든 칸이 빈 문자열인 틀
note['S']['cc'] = 'C.C : 인후통\nOnset : 내원 1일 전\n통증평가 : NRS 4점, 부위 목, 양상 따끔거림'
note['S']['ros'] = 'Fever/Chill (+/-)  Cough (+)\nDyspnea (-)'
note['O']['exam'] = 'V/S : BT 37.3℃ (턴 3)\nH/E/E/N/T : 인두 발적 (+) (턴 4)'
note['A']['evidence'] = '#1. 급성 인두염\n- 근거 : 1일 전 시작된 인후통, 인두 발적'
note['P']['disposition'] = '외래 경과 관찰'
client.diagnose(note=note, diagnosis='급성 인두염')
```

HTTP로 보낼 때는 `{"action": "DIAGNOSE", "request_id": ..., "note": {"S": {...}, "O": {...}, "A": {...}, "P": {...}}, "diagnosis": "..."}` 형식입니다. 칸이 하나라도 빠지거나 다른 칸이 있으면 `INVALID_RECORD_FIELDS`로 거절되고 턴은 쓰지 않습니다.

### 확인한 사실만 기록하기

- **없음·음성**: 실제 질문·확인 또는 제공된 결과가 있을 때만 사용합니다.

- **미확인**: 아직 질문하거나 정보를 얻지 못했습니다. 항목형 칸에서는 `Allergy ( )`처럼 괄호를 비워 둡니다.

- **미시행**: 해당 진찰·검사를 수행하지 않았습니다.

- **계획**: 앞으로 할 일입니다. 이미 시행한 결과처럼 적지 마세요.

물어보거나 진찰한 내용을 S·O 칸에 기록까지 해야 가장 높게 인정됩니다. 물어보지 않은 내용을 적어도 인정되지 않고, 확인한 내용과 다르게 적으면 감점됩니다. 기록에 교육 계획을 쓰는 것과 환자에게 실제로 설명하는 것도 다릅니다. 내부 사고 과정 전문은 필요하지 않으며 사실과 판단을 연결하는 간결한 근거를 쓰면 됩니다.

기록 전체는 UTF-8 100,000바이트, 주진단은 500바이트까지 보낼 수 있습니다. 칸별 분량 제한은 없습니다.

<a id="examples"></a>

## 기록 작성 예시

아래는 칸 사용법과 사실·판단·계획 구분을 설명하기 위한 가상 예시입니다. 실제 대회 증례나 정답·만점 기록이 아닙니다.

### 문진·진찰 내용을 칸에 나눠 적기

**확보한 내용:** 환자가 "어제부터 목이 아파요", "기침도 조금 나요"라고 답했습니다. 3턴에 체온 37.3℃, 4턴에 인두 발적을 확인했습니다. 약물·알레르기와 위험 증상은 아직 확인하지 않았습니다.

```
[S] 주호소: C.C : 인후통
          Onset : 내원 1일 전
          통증평가 : 도구 NRS, 점수·양상 미확인
[S] 현병력: 내원 1일 전 시작된 인후통으로 내원함. 기침 조금 동반. 악화·완화 요인 미확인.
[S] 과거력·약물·알레르기: DM / HTN ( / )  Medicine history ( )  Allergy ( )
[S] 계통 문진: Cough (+)  Fever/Chill ( / )  Dyspnea ( )
[O] 진찰 소견: V/S : BT 37.3℃ (턴 3), 나머지 미측정
          H/E/E/N/T : 인두 발적 (+) (턴 4)
[A] 주진단: 급성 인두염
[A] 근거: #1. 급성 인두염
          - 근거 : 1일 전 시작된 인후통, 인두 발적
[A] 감별진단: r/o 세균성 인두염 : 편도 삼출물·경부 림프절 미확인
[P] 추가 검사: 위험 징후 확인 후 필요 시 판단
[P] 추적: 추가 문진과 진찰 결과에 따라 결정
(빈 칸은 생략해 표시함, ( )는 아직 확인하지 않은 항목)
```

이 예시는 미확인 정보를 남기는 방법을 보여 줍니다. 필요한 질문을 충분히 수행했다는 의미는 아닙니다.

### 본선 형식 예시: 검사 값·판단·계획 구분

**가상으로 제공된 정보:** 피로와 어지럼, 과다 월경 병력이 확인되었습니다. 9턴에 받은 검사 결과는 Hb 9.8g/dL (참고 12.0–16.0), MCV 72fL (참고 80–100), ferritin 8ng/mL (참고 15–150)입니다.

```
[S] 주호소: C.C : 피로, 어지럼
[S] 현병력: 과다 월경 있어 왔으며 피로와 어지럼으로 내원함. 기간·정도와 다른 출혈 증상은 미확인.
[O] 검사 결과: Hb 9.8g/dL (L), MCV 72fL (L), ferritin 8ng/mL (L) (턴 9)
[A] 주진단: 철결핍성 빈혈
[A] 근거: #1. 철결핍성 빈혈
          - 근거 : 소구성 빈혈, ferritin 감소, 과다 월경
[A] 감별진단: r/o 다른 출혈 원인 : 위장관 출혈 증상 추가 확인 필요
[P] 추가 검사: 출혈 양상에 따른 추가 평가
[P] 추적: 결과에 따라 관리·추적 계획 결정
(빈 칸은 생략해 표시함)
```

수치·단위·참고범위는 환경이 제공한 것을 그대로 기록하세요. 증례에 없는 값을 정상이라고 채우거나 추정 원인을 확정 사실로 쓰지 않습니다.

<a id="package"></a>

## 코드 제출 · 실행 계약

```
submission.zip
├── run.py
├── requirements.txt
└── nova_sdk.py
```

코드 ZIP은 최대 50,000,000바이트, 해제 후 500,000,000바이트, 파일 5,000개입니다. 암호화·심볼릭 링크·경로 이동·중복 경로를 포함하면 반려됩니다. 서버가 표준 실행 이미지를 만들므로 참가자 Dockerfile은 제출하지 않습니다.

추가 의존성은 `requirements.txt`에 PyPI(pypi.org) 패키지를 `name==version`으로 한 줄씩 적습니다. 서버는 제출 버전을 처음 평가할 때 PyPI에서 미리 빌드된 휠(.whl)을 받아 설치하고, 그 이미지를 이후 평가에 사용합니다. 3일 넘게 평가에 쓰이지 않은 이미지는 지우고, 다음 평가 때 같은 고정 버전으로 다시 빌드합니다. URL·Git 주소, 다른 패키지 저장소(예: download.pytorch.org), 소스만 배포되는 패키지(예: flash-attn)는 설치할 수 없습니다.

실행 중에는 인터넷이 차단됩니다. Hugging Face 모델·임베딩 가중치, nltk·spaCy 데이터처럼 처음 사용할 때 내려받는 자료는 실패하므로 ZIP에 넣고(본선은 모델 ZIP) 로컬 경로에서 읽으세요. 시작 패키지의 `local.Dockerfile`로 서버와 같은 규칙의 빌드와 인터넷 없는 준비 단계를 미리 확인할 수 있습니다. 증례마다 새 실행 상태가 제공되며 다른 증례의 캐시·파일·통계를 이어서 사용할 수 없습니다.

예선에서는 증례마다 지정 Doctor API(`client.chat()`)를 최소 1회 호출해야 하며, 호출이 없는 증례는 0점입니다. 증례마다 최대 200회, 입력 500,000·출력 100,000토큰까지 호출할 수 있습니다. `client.chat(messages, max_tokens=2048, reasoning_effort="low")`처럼 호출마다 추론 강도를 `low`·`medium`·`high` 중에서 고를 수 있습니다. 높을수록 오래 생각해 출력 토큰과 비용이 늘고(효율 점수에 반영), 추론 토큰도 `max_tokens`에 포함되므로 `high`에는 넉넉한 `max_tokens`가 필요합니다. `temperature`도 0~2 사이에서 정할 수 있습니다(예: `temperature=0.7`). 운영진 측정에서는 0으로 해도 매번 같은 답이 나오지 않았고, 낮출수록 빈 답이 늘었습니다. 둘 다 지정하지 않으면 모델 기본값을 사용합니다. 단순 연결 예제의 출력을 그대로 고정 답안으로 사용하지 말고 문진·진찰 결과에 따라 판단하도록 구현하세요.

 [코드 제출하기](https://nova.snubhai.org/submissions/)  

<a id="finals"></a>

## 본선 모델 등록 · 재사용

본선 참가팀은 코드 ZIP과 별도로 모델 ZIP을 최대 32GB까지 등록하고 PPT/PPTX를 첨부합니다. 필요한 가중치·토크나이저·설정·어댑터를 모델 ZIP 루트에 포함하세요. 한 번 등록한 모델은 이후 코드 버전에서 다시 선택할 수 있습니다.

```
import os

model_dir = os.environ["NOVA_MODEL_DIR"]
# prepare()에서 이 로컬 디렉터리의 모델·토크나이저를 로드합니다.
# consult()에서는 준비된 참가자 모델로 추론합니다.
```

서버가 선택한 모델을 읽기 전용 경로에 연결합니다. 본선 에이전트는 직접 로드한 모델을 사용하며 예선 Doctor 호출인 `client.chat()`을 사용하지 않습니다. 실행 중 모델을 내려받거나 GPU 두 장을 합쳐 사용할 수 없습니다. A6000 48GB급 GPU 한 장에 실행 메모리까지 포함해 로드되어야 합니다.

업로드 화면은 파일 해시를 계산하고 분할 전송합니다. 중단되면 같은 브라우저에서 같은 파일을 다시 선택해 재개하세요. 파일 이름이 같아도 내용이 달라지면 새 모델 자산으로 등록됩니다.

<a id="errors"></a>

## 문제 해결

| 상태·오류 | 확인할 내용 |
| --- | --- |
| 로그인 메일이 오지 않음 | 등록 이메일·스팸함과 메일 서비스 상태를 확인하세요. |
| `INVALID_API_RESPONSE` (HTTP 403, `error code: 1010`) | Cloudflare가 Python 기본 User-Agent(`Python-urllib`)의 요청을 막은 것입니다. 시작 패키지를 다시 내려받아 `nova_sdk.py` 1.0.1 이상을 쓰거나, 기존 `nova_sdk.py`의 요청 헤더에 `'User-Agent': 'nova-sdk/1.0.1'`을 추가하세요. |
| `CONTENT_TOO_LONG` · `EMPTY_CONTENT` | 공백·문장부호 포함 NFC 30자 제한과 빈 내용을 확인하세요. SAY·EXAM은 1턴을 사용합니다. SDK는 30자를 넘는 말을 보내기 전에 막습니다. |
| `EXAM_NOT_SPECIFIC` | 진찰 동작 하나만 구체적으로 요청하세요. 답은 없지만 1턴을 사용합니다. |
| `TEST_NOT_SPECIFIC` | 검사 하나만 구체적으로 요청하세요(본선). 턴은 사용하지 않습니다. |
| `EXAM_NOT_RECOGNIZED` | 신체진찰이 아닌 요청(문진·혈액·영상 검사·처치·기록 등)이거나 존재하지 않는 진찰입니다. 진찰 동작 하나를 요청하세요. 답은 없지만 1턴을 사용합니다. |
| `TEST_NOT_OFFERED` | 대회에서 제공하지 않는 검사입니다(본선). 턴은 사용하지 않습니다. |
| `ACTION_NOT_AVAILABLE` | 예선에서는 TEST(혈액·영상 검사)를 받지 않습니다. 턴은 사용하지 않습니다. |
| `PROVIDER_RESPONSE_INVALID` · `PATIENT_RESPONSE_INVALID` · `EXAMINER_RESPONSE_INVALID` | Doctor 모델이 빈 답을 냈거나, 가상 환자·진찰 판정 모델이 형식에 맞는 답을 내지 못한 경우입니다. 요금과 턴을 쓰지 않으니 새 요청으로 다시 보내세요(기본 에이전트 참고). 공식 평가 중에도 같습니다. Doctor 모델의 빈 답은 증례당 호출 200회에는 포함됩니다. |
| `MODEL_NOT_ALLOWED` | 진료 세션 안에서 Doctor 모델(`gpt-6-luna`) 외의 모델을 지정했거나, 쓸 수 없는 모델 이름입니다. 개발용 모델은 세션 밖에서만 부를 수 있습니다. |
| `MODEL_CALL_LIMIT` · `MODEL_TOKEN_BUDGET` | 이 증례의 Doctor 모델 호출 200회 또는 토큰 한도(입력 500,000·출력 100,000)를 다 썼습니다. 지금까지의 내용으로 기록을 작성해 DIAGNOSE로 마치세요. 진료 세션 밖이라면 팀의 하루 한도(gpt-6-luna 1,000회, gpt-6.1-sol 100회)를 다 쓴 것이며 KST 자정에 초기화됩니다. 오류로 끝난 호출(빈 답, 제공자 장애, 시간 초과)은 이 하루 한도에 세지 않습니다. |
| `PROVIDER_UNAVAILABLE` | 모델 서비스의 일시 장애이거나, Doctor 모델이 **180초** 안에 답을 시작하지 못한 경우입니다(`reasoning_effort`가 높고 출력이 길면 걸리기 쉽습니다). 개발 중이든 평가 중이든 잠시 뒤 **같은 request_id**로 다시 보내세요. 재시도하지 않고 멈추면 실행 실패로 기록됩니다. |
| `REQUEST_PENDING` | 같은 request_id의 Doctor 호출이 아직 처리 중이거나(503), 이 증례에서 다른 Doctor 호출이 진행 중입니다(409). 잠시 뒤 같은 request_id로 다시 보내면 끝난 답을 그대로 받습니다. 클라이언트 대기 시간은 서버 한도(180초)보다 길게 두세요(새 SDK 기본값 240초). |
| `SAMPLE_VALIDATION_FAILED` | 공개 샘플 중 실행이 실패했거나 기록을 제출하지 못한 증례가 있습니다. 제출 상세의 **증례별 결과**에서 증례마다 사유(실행 오류·시간 초과·메모리 초과·기록 미제출·Doctor 미호출)와 오류 출력(stderr) 마지막 부분을 볼 수 있습니다. 리더보드 평가는 비공개 증례라 사유만 보여 줍니다. 개발 키트와 시작 패키지의 `local.Dockerfile`(인터넷 없이 읽기 전용으로 실행)로 재현해 보세요. |
| 서버 장애 (운영진이 확인) | 증례별 결과에 이 표시가 있으면 참가자 코드가 아니라 평가 서버 쪽 문제로 실행이 멈춘 것입니다(평가 API 연결 끊김·응답 지연, 모델 설정 변경 등 사유와 코드가 함께 표시됩니다). 운영진이 확인해 같은 제출을 다시 실행하며, 이 실행은 일일 평가 횟수에서 차감하지 않습니다. 고칠 코드는 없습니다. |
| `SAMPLE_DAILY_LIMIT` | 개발 샘플 세션을 오늘 팀 한도(100개)만큼 만들었습니다. 한국시간 0시에 초기화됩니다. 그동안은 개발 키트로 시험하세요. |
| `DEPENDENCY_DOWNLOAD_FAILED` | `requirements.txt`의 패키지·버전이 PyPI에 휠로 있는지 확인하세요. `local.Dockerfile` 빌드에서 같은 오류를 확인할 수 있습니다. |
| `DEPENDENCY_BUILD_FAILED` | 받은 휠의 설치가 실패했습니다. 패키지 간 버전 충돌을 확인하세요. |
| `DEPENDENCY_DOWNLOAD_TOO_LARGE` · `BUILD_TIMEOUT` | 의존성 용량(휠 합계 8GB) 또는 빌드 시간(20분)을 넘었습니다. 필요 없는 패키지를 빼세요. |
| 빌드·검증 실패 | ZIP 루트의 필수 파일과 SDK 사용법을 확인하세요. |
| 리더보드 제출 불가 | 접수 기간과 팀의 당일 잔여 횟수를 확인하세요. 샘플 검증은 필수가 아니지만, 먼저 해 두면 실행 실패로 공식 평가 횟수를 잃는 일을 줄일 수 있습니다. |
| 서비스 장애·정산 대기 | 임의의 점수·비용으로 대체하지 않습니다. 처리 상태를 다시 확인하세요. |

운영 문의 시 팀명, 제출 버전, 표준 오류 코드를 알려 주세요.

 [[email protected]](https://nova.snubhai.org/cdn-cgi/l/email-protection#e3828a908d96818ba3848e828a8fcd808c8e)
