# 임상 KB와 온톨로지 통합

팀 PR #1 head `64d3c0b`와 로컬 `fe1a839`를 통합했습니다. 팀원이 작성한 임상 지식과 데이터 출처 기록은 [SOURCES.md](SOURCES.md)에 보존합니다. 임상 규칙과 온톨로지 관계 모두 임상 검수 전이며 질환 수·자기일관성 테스트 통과를 진단 정확도 개선으로 해석하지 않습니다.

## 역할과 실행

- `MedDB`: 주호소별 후보·문진·진찰·SOAP 초안. 임상 스키마는 [clinical-schema.md](clinical-schema.md).
- `KB`: 질환–기전–소견 관계와 출처·검수 상태·고정 버전. 스키마는 [ontology-schema.md](ontology-schema.md).
- `KnowledgeBridge`: 명시적 소견 ID 매핑으로 관찰을 전달하고 각 KB의 근거를 별도로 제공합니다. 점수를 합산하지 않습니다.

기존 웹·CLI는 유지하고 임상 명령은 별도 하위 명령으로 제공합니다.

```powershell
python -m meddb clinical validate
python -m meddb clinical stats
python -m meddb clinical demo "기침이 있어요"
python -m meddb clinical page docs/viewer.html
python -m meddb serve
```

`examples.hybrid_agent.consult`는 `knowledge_mode` 인자 또는 `NOVA_KNOWLEDGE_MODE`로 `clinical`(기존 기본), `ontology`, `integrated`를 선택합니다. 같은 LLM 진료 루프와 표준 진찰 문장을 사용합니다. `ontology`는 임상 후보·행동 추천과 임상 SOAP 초안을 사용하지 않고 온톨로지 근거를 LLM에 제공합니다. `integrated`는 두 KB의 힌트를 함께 제공합니다. 이것은 동일한 진료를 보장하는 것이 아니라 비교할 지식 입력을 구분하는 설정입니다.

```powershell
$env:NOVA_KNOWLEDGE_MODE = "integrated"
$env:NOVA_REFERENCE_PROFILE = "research"
```

참고 프로필 기본값은 `reviewed`입니다. 현재 매핑 5개는 모두 `draft`이므로 기본값에서는 전달되지 않습니다. `research`에서만 초안 매핑을 사용하며 응답에 상태·매핑 버전·원문 근거를 표시합니다. 복합 소견인 구역·구토나 수식된 흉통을 구토·흉통 전체로 자동 매핑하지 않습니다. 환자 정보 추출은 휴리스틱/모델 판정이므로 의미 정확성의 임상 승인을 뜻하지 않습니다. 인구학 정보와 질병 ID의 교차 매핑은 아직 연결하지 않았습니다.

## 수정한 경계 사례

- 모르겠다는 답변은 `unknown`으로 유지합니다.
- 일부 진찰 소견의 `(-)`를 다른 소견의 음성으로 확대하지 않습니다.
- 성공한 진찰도 판독이 불명확한 개별 소견은 확인되지 않은 상태로 남기며 추가 확인 후보에 남깁니다.
- 거절된 진찰을 성공한 진찰로 기록하지 않습니다. 하이브리드 Tracker는 시도/성공/거절 이력을 별도로 보존합니다.
- 상충하는 진술은 양성·음성 근거에서 빼고 재확인 대상으로 표시합니다. 추출 원문과 턴 번호를 이벤트로 보존합니다.
- 최종 진단 변경 시 해당 진단으로 A/P를 다시 만듭니다. 미등록 진단에 다른 질병의 계획을 재사용하지 않습니다. LLM의 사실 추출·기록 내용 전체의 임상 타당성을 검증한 것은 아닙니다.

## 검증과 패키징

```powershell
python -m unittest discover -s tests -q
python tools/compare_integrated_knowledge.py
python tools/package_agent_knowledge.py
python tools/make_submission.py --starter data/external/starter/run.py --agent hybrid --knowledge-mode integrated --reference-profile research
```

오프라인 재생은 불명확한 발열·호흡기 소견·발열 정정 3개 경계 사례를 3가지 지식 입력으로 비교합니다. 모델 호출은 0회이며 실제 진단 정확도·SOAP 점수·비용·턴 수를 측정하지 않습니다. 별도 독립 증례와 실제 모델을 사용하는 비교는 다음 검증 단계입니다.

제출 ZIP은 런타임 코드·임상 데이터·현재 참고 KB 릴리스·명시적 설정과 출처 문서만 포함합니다. 공개 샘플·평가 정답·PPT·진료지침 본문을 넣지 않습니다. 공식 starter/SDK는 로컬에 있어야 하며 이 저장소에서 새로 배포하지 않습니다. 포함된 외부 임상 데이터의 출처·이용 조건은 팀원의 장부를 확인하고 대회 제출 전 최종 확인해야 합니다.
