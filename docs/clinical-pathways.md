# 출처 기반 진료 지식 보강

불면·수면제 사용, 아동 성장 상담, 갑상선 과다 기능 관련 문진·감별·계획 요구사항 12개를 `data/agent/clinical-pathways.json`에 추가했다. 원문 출처는 [Alliance for Sleep 지침](https://europepmc.org/article/MED/37048577), [Pediatric Endocrine Society 의뢰 지침](https://pedsendo.org/clinical-resource/child-with-suspected-short-stature/), [NIDDK Graves 안내](https://www.niddk.nih.gov/health-information/endocrine-diseases/graves-disease)다. 공개 증례의 대본·모범 기록을 읽는 런타임 코드는 없다.

요구사항은 질문·진찰·계획 제안이다. 환자에게 확인된 소견이나 자동 진단 규칙이 아니며 모두 임상 검수 전 초안이다. 모델이 임의로 치료 용량을 정하거나 검사 계획을 시행 결과로 기록하지 않도록 분리했다. 예선에서는 검사 실행이 아니라 계획만 작성해야 한다.

아동 성장과 청소년 사춘기 평가를 구분한다. 호출자가 확인한 환자 맥락을 `patient.puberty_assessment`로 전달한다: appropriate/not_age_appropriate/unknown. 나이 숫자만으로 자동 판정하지 않는다. not_age_appropriate이면 Delayed puberty 소견을 점수에서 제외하고 해당 질문을 제안하지 않는다. appropriate으로 명시하지 않으면 직접 사춘기 지연 질문의 실행 템플릿을 보류한다. 이 필드는 질환 자체를 제외하는 규칙이 아니다.

`meddb.pathways.recommend()`는 확인한 문진 항목의 evidence_id/value가 있으면 해당 질문을 반복하지 않는다. 단순 질문 실행이나 빈 응답을 완료로 처리해서는 안 된다. 여러 하위 질문을 가진 요구사항의 confirmed는 전체 요구사항을 확인한 경우에만 기록한다.

점검표의 missing_pathway 감소는 연결된 초안 요구사항이 생겼다는 뜻이며, 임상적 타당성이나 진단 성능 개선을 검증한 결과가 아니다.
