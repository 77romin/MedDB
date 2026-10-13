# 에이전트 연결 및 1~5단계 진행 결과

2026-10-13. 기존 의료 릴리스는 변경하지 않았다. 출처를 읽었다는 이유로 의학 검수를 완료한 것으로 표시하지 않았다.

## 1. 부정 관계와 맥락

`relation_polarity()`가 명시적 polarity 또는 기존 EXCLUDED 문자열을 처리한다. 양성·부정 관계가 상충하면 해당 소견은 점수에서 제외하고 uncertain으로 전달한다. 각 점수의 출처와 적용 맥락을 함께 반환한다. EXCLUDED 21개를 `agent-knowledge-audit.json`의 검수 대기 목록에 기록했다. 특히 특정 질환 변형·발병 단계에만 적용되는 부정 관계는 임상 검수 전이며 범용 배제 규칙으로 확정하지 않는다.

수입 코드는 다음 재수입부터 설명 길이와 문헌 참조 수를 자르지 않고 modifier/onset/severity/sex/notes를 보존한다. 고정 원본 checkout이 현재 없으므로 재수입은 실행하지 않았고, 이전 자료의 이미 잘린 정보가 복원된 것은 아니다.

## 2. 데이터 사용 정책

| profile | 사용 범위 | 현재 관계 |
|---|---|---:|
| reviewed | 검수 완료만 | 0 |
| pilot | 기존 NIDDK 복통 파일럿 초안 | 50 |
| research | 전체 연구용 초안 | 114,088 |

API의 기본 정책은 reviewed다. 웹은 초안을 명시적으로 포함하는 개발 화면이다. team이 사용할 정책을 결과와 로그의 policy.name으로 고정한다. 파일럿은 범위를 줄이는 실험이며 임상 검수판이 아니다. 팀원에게 메시지를 보내거나 이 정책에 합의했다는 기록은 만들지 않았다.

## 3. 한국어 표현과 커버리지

표현 사전 24항목이 새 기본 판의 소견에 연결된다. 부정·기간·과거·가족력·문장 간 충돌을 보수적으로 처리한다. 정규화 결과는 제안이며 자동으로 관찰 상태를 바꾸지 않는다. 모호한 표현을 unknown으로 남기고 unmatched도 보존한다. 웹에서 소견과 상태를 확인한 후 적용한다.

기간은 문자열로만 보존하며 확률·배제 규칙에 반영하지 않는다. 한국어 전체를 이해하는 언어 모델이 아니므로 새로운 표현은 사전을 보강하거나 에이전트가 원문과 대조해야 한다.

공개 예시의 수면제 의존 관련 명칭은 현재 그래프에서 찾는 경로가 부족하다. 이를 coverage gap으로 기록했고 불면 시 수면제 이름을 확인하는 질문을 제안한다. 공개 예시 하나로 의존 진단 규칙이나 새 질환–증상 확정 관계를 만들지는 않았다. 전체 대회 주호소 목록이나 추가 공개 증례를 받으면 범위 표를 확대해야 한다.

## 4. 다음 질문·진찰·위험 신호

```python
from meddb import KB
kb = KB()
proposals = kb.normalize('열이 없어요; 기침이 있어요')
# 원문과 대조하고 확인한 상태만 아래 observations에 반영한다.
result = kb.suggest(
    {'nova:vomiting':'present', 'nova:fever':'absent'},
    profile='pilot', patient={'age':35,'sex':'female'}, limit=5,
)
```

`POST /api/normalize`와 `POST /api/suggest`, `KB.call()`에서도 사용할 수 있다. 기존 rank API는 유지한다.

추천은 상위 10개 후보 사이에 양성·부정 관계가 어떻게 분포하는지와 템플릿 유무를 사용한다. 분리 점수는 구조적 비교 점수이며 기대 정보량·진단 확률이 아니다. 상위 후보 절단과 자료의 불완전성이 영향을 준다. 관계가 기록되지 않은 질환을 해당 소견이 없는 질환으로 취급하지 않는다.

20개 초안 행동 템플릿을 추가했다. SAY는 한 번에 하나의 확인 질문이며 30자 이하다. Wheezing의 폐 청진 EXAM 템플릿은 대회 서버가 인정하는지 아직 확인하지 않았다. 없는 템플릿은 실행 행동을 임의 생성하지 않고 action=null을 반환한다.

위험 신호 체크리스트의 상복부 통증+호흡곤란 조합은 [NIDDK 췌장염 안내](https://www.niddk.nih.gov/health-information/digestive-diseases/pancreatitis/symptoms-causes)의 신속한 진료 안내를 바탕으로 작성한 로컬 검수 전 제안이다. 췌장염 진단 규칙이나 포괄적인 응급 분류 시스템이 아니다. 약물 용량·처치 결정·치료 권고를 자동 생성하지 않는다.

### 에이전트 팀 연결 계약

- `prepare()`에서 KB를 로드한다. 실행 중 인터넷 다운로드를 하지 않는다.
- `consult()`에서 실제 답변과 진찰 결과로 observations를 갱신한다. 질문만 했다고 소견 있음으로 기록하지 않는다.
- normalize 제안을 확인한 뒤 상태를 반영하고 suggest를 호출한다.
- 반환한 일반 의료 지식을 환자에게 확인된 사실로 SOAP에 복사하지 않는다.
- 점수와 추천은 모델의 판단 보조다. EXAM 오류나 템플릿 누락을 처리하고 남은 턴·마감 시각은 NOVA SDK 응답을 따른다.
- 로그에 데이터 version/hash, policy/hash, score_method, 사전 hash를 기록한다. 실제 환자 발언과 observation 변경 근거를 연결한다.

`examples/agent_knowledge.py`는 짧은 결과를 반환하는 연결 예제다. 완성된 Doctor Agent나 제출용 run.py는 아니다.

## 5. 비교 평가

```powershell
python tools/audit_agent_knowledge.py
python tools/evaluate_agent_knowledge.py
python tools/evaluate_agent_knowledge.py --agent-logs path/to/logs.json
```

합성 회귀 사례 6개 × 기존 공통점 순위 / 가중 근거 순위 / 파일럿 워크플로 = 18회 비교를 실행했다. 기존 KB의 관계로 구성한 구현 검증용 사례이므로 임상적 독립 평가나 대회 일반화 성능으로 해석하지 않는다. 결과는 `docs/agent-evaluation.json`이다.

실제 Doctor Agent의 KB 없음 / 이전 KB / 개선 KB 비교는 아직 실행하지 않았다. 이 저장소와 상위 개발 폴더에서 Doctor Agent 코드·NOVA SDK·개발 증례를 찾지 못했다. 모델 비용·진료 턴·SOAP 평가를 KB 조회 시간으로 대체하지 않았다.

이후 사용자가 열어 둔 공식 사이트에서 SDK·기본 에이전트·공개 증례 3건·진료지침 15,904개를 확보했다. 공식 기본 에이전트는 확인했지만 실제 모델 호출은 실행하지 않았다. 사이트 자료를 활용한 후속 작업과 커버리지 검사는 [공식 지침 연결 문서](nova-guidelines-integration.md)를 참고한다.

실제 비교 로그의 형식:

```json
[
  {"arm":"no_kb","case_id":"C01","correct":false,"turns":20,"model_cost":0.15,"latency_seconds":80},
  {"arm":"previous_kb","case_id":"C01","correct":false,"turns":18,"model_cost":0.16,"latency_seconds":83},
  {"arm":"improved_kb","case_id":"C01","correct":true,"turns":16,"model_cost":0.14,"latency_seconds":75}
]
```

위 숫자는 입력 형식 예시이며 실제 성능 결과가 아니다. correct는 독립적인 정답 판정 결과여야 한다. 세 조건 모두 실행한 같은 case_id만 비교한다. 중복은 거부하고 미측정 비용을 0으로 처리하지 않는다. 비용 단위는 모든 실행에서 동일하게 정한다. 최종 대회 점수와 의사소통·안전·기록 품질도 별도로 확인해야 한다.

## 전달용 번들

```powershell
python tools/package_agent_knowledge.py
```

`dist/nova-knowledge-bundle.zip`은 Python 코드, 최신 압축 KB 한 판, 정책·표현·행동 사전, 연결 예제와 출처 고지를 포함한다. 원본 PPT·옛 릴리스·웹 탐색기·평가 사례는 포함하지 않는다. 압축 내부 데이터는 기본 KB()로 읽을 수 있다. 대회 제출 ZIP에 합칠 때는 별도의 run.py와 requirements.txt가 필요하다.

같은 버전의 기본 JSON과 기존 압축 릴리스는 JSON 내용은 동일하나 바이트 해시가 다르다. 번들은 기본 JSON의 원래 바이트를 그대로 압축하여 현재 실행의 data_sha256을 유지한다. manifest에서 실제 해시를 확인한다.

## 확인 결과와 남은 작업

Python 테스트 총 55개 중 51개 통과, RDF/SHACL 의존성 미설치로 4개 skip. 실제 HTTP handler의 정규화·추천·입력 오류·새 웹 스크립트 응답을 소켓 없이 테스트했다. JavaScript 문법 검사와 기존 그래프 테스트도 통과했다. 번들을 임시 폴더에 풀고 별도 Python 프로세스에서 KB 로딩·연결 예제 실행·데이터 해시를 확인했다.

로컬 서버를 브라우저로 열려고 했으나 연결 시간 초과가 발생했고, 로컬 HTTP 접속도 샌드박스 소켓 제한 및 승인 후 시간 초과로 실행되지 않았다. 따라서 브라우저 화면의 시각 검수와 실제 소켓을 통한 전체 흐름을 확인했다고 보고하지 않는다.

남은 작업: 부정 관계 및 행동 템플릿의 임상 검수, 대회 질환군 커버리지 확대, 검수된 환자 조건 데이터, 실제 Doctor Agent/SDK/공개 증례를 사용한 세 조건 진료 평가. 1~4단계의 개발 구현과 5단계의 비교 도구·회귀 실행을 완료했지만, 실제 임상 검수와 에이전트 성능 검증은 아직 완료하지 않았다.
