# 단계 4: 오프라인 검증과 실제 비교 실행 도구

사용자의 선택에 따라 이번 작업에서는 모델/API 호출을 하지 않는다. 실제 정확도·진료 턴·SOAP 평가·모델 비용을 측정했다고 보고하지 않는다.

## 이번에 실행한 비교

`tools/compare_knowledge_offline.py`는 이전 KB 커밋 `9711bb8`과 3단계 완료 커밋 `d766fd4`의 파일을 `.run/knowledge-comparison`에 따로 고정한다. 의료 데이터뿐 아니라 코드와 정책·사전까지 커밋 파일 해시로 확인한다. 같은 의료 데이터 버전이라도 코드·정책 변경을 구분한다.

공개 증례 3건에서 평가자가 확인한 일부 시작 정보·진찰표 소견을 직접 제공하고 세 조건(없음/이전/개선)을 9회 실행했다. 이는 참고 사실 재생이며 에이전트가 환자에게 질문해 얻은 결과가 아니다. 정답 진단은 입력하지 않았고 정확도는 산출하지 않는다. 표의 시간은 단일 실행의 KB 조회 시간이며 준비 시간·모델 응답 시간·진료 시간은 포함하지 않는다. KB 없는 조건의 조회 시간은 측정 대상이 없어 null이다.

결과는 `docs/offline-knowledge-comparison.json`과 `.md`에 있다. 새 문진·계획 요구사항이 제공되는지 확인했지만 응답이 더 커졌으므로 효율 개선으로 주장하지 않는다. 모델 전달량과 실제 진료의 효과는 별도 실험이 필요하다.

## 실제 에이전트 실행 준비

같은 에이전트 코드가 `examples/ablation_support.py`의 provider를 호출하고 아래 환경변수를 따른다.

- NOVA_KB_MODE: no_kb / previous_kb / improved_kb
- NOVA_KB_SNAPSHOT_DIR: 고정 KB 경로
- NOVA_COMPARISON_CASE_ID: 실행할 증례 ID. 정답 조회나 고정 진단 선택에 사용하지 않는다.

```powershell
python tools/run_agent_ablation.py --agent-command-json '["python","team_agent.py"]' --cases C01 C03 C10
```

기본은 plan-only다. 모델 실행이나 인증정보 조회 없이 `.run/agent-ablation/plan.json`에 동일 에이전트 명령의 9개 작업을 만든다. team_agent.py는 팀이 연결할 프로그램 자리이며 이 저장소에 완성된 프로그램이 있다는 뜻이 아니다.

나중에 실행 환경·모델·비용 한도를 정하고 에이전트의 모드 연결을 확인한 뒤에만 `--execute`를 명시한다. 에이전트 명령은 같은 모델 설정과 질문 정책을 유지하고, stdout에 case_id/arm/diagnosis와 실제 측정한 지표를 담은 JSON 하나를 반환한다. 비용·지표를 측정하지 못하면 필드를 생략하며 0으로 채우지 않는다. API 호출 비용 한도는 해당 에이전트/API 실행부에서 관리해야 하며 이 runner가 비용을 추정해 차단하는 도구는 아니다.

독립 판정자가 correct를 추가한 로그만 기존 `tools/evaluate_agent_knowledge.py --agent-logs ...`로 평가한다. 현재 실제 에이전트 실행 결과는 없다.

이전 API 응답은 공통 형태로 변환하지만 새 관찰·문진·맥락 계약을 지원하지 않는다는 경고를 남긴다. 개선 조건만 추가 문진·계획 정보를 받는다. 따라서 이는 KB 제공 기능 전체의 비교이며 특정 그래프 관계 하나의 효과를 분리하는 실험은 아니다.
