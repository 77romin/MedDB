# 에이전트 팀 조회 규약 v1

팀에 전달할 구현 규약이다. 외부 팀원에게 메시지를 보내거나 합의 완료로 표시하지 않았다.

`KB.assist()` / `KB.call('assist',...)` / `POST /api/assist`가 동일한 입력을 받는다. JSON 스키마는 `data/agent/assist-schema.json`이다. 기본 정책은 reviewed이며 초안 개발에서는 research를 명시한다.

```python
from examples.knowledge_session import KnowledgeSession
session = KnowledgeSession(profile='research')
# SDK가 실제 반환한 환자 답변 또는 진찰 결과만 기록한다.
event = session.record_result('say', 1, '잠을 잘 못 자요')
# 모델/사람이 원문과 대조하여 의미 매핑을 확인한 후 호출한다.
session.confirm_observation('hpo:HP:0100785', 'present', [event])
support = session.support()
```

1. prepare에서 KB를 로드한다. 증례별로 KnowledgeSession을 새로 만든다.
2. initial은 제공된 시작 정보, say/exam/test는 성공한 SDK 응답 내용이다. 질문만 보냈거나 요청이 실패한 경우에는 관찰 증거를 만들지 않는다.
3. 있음/없음은 기존 이벤트를 참조해야 한다. 미확인은 증거를 꾸며 넣을 필요가 없다. 중복·존재하지 않는 이벤트와 소견, 예선의 검사 결과는 거부한다.
4. 나이·성별·사춘기 평가 적절성도 patient_evidence로 출처 이벤트에 연결한다. 사춘기 적절성은 연령 숫자만으로 정하지 않는다.
5. history 완료는 요구사항 전체를 확인한 경우에만 기록한다. 같은 evidence_id/value를 결과에 남겨 추적한다. 계획을 수행 결과로 바꾸지 않는다.
6. 계약 검증은 참조·형식을 확인하며 문장의 의학적 의미나 모델의 매핑이 참인지 판정하지 않는다. 이 부분은 에이전트·검수자가 대조한다.

응답에는 계약 버전, 데이터 해시, 점수 방식, 정책 해시, 관찰의 출처, 후보와 지지/반박 근거, 다음 소견 확인, 미완료 문진·진찰·계획이 있다. 확률은 반환하지 않는다. 일반 의료 지식은 S/O에 관찰 사실로 복사하지 않는다.

모델용으로 후보 수를 제한하고 각 근거의 context를 300자 원문 일부로 반환한다. 생략 수와 잘림 여부, 원문 위치를 명시한다. 원본 지식은 KB에 보존하며 필요한 경우 graph/원문 지침 조회로 확인한다. 경고·환자 사실·출처를 지우고 첫 후보만 전달하지 않는다.

여러 질문을 가진 요구사항에서는 다음 질문 하나를 선택한다. 문진 완료 여부를 고려해 이미 확인한 항목을 반복하지 않는다. 한 번의 짧은 답변이 요구사항 전체의 완료를 뜻하지 않는다.

NOVA SDK의 남은 턴과 마감 시각은 KB 밖에서 관리한다. 모델 호출 최소 조건, 재시도, 최종 SOAP 작성·DIAGNOSE는 에이전트의 책임이다. 검수 전 제안이 대회 서버에서 항상 인정되는 진찰이라는 보장은 없다.
