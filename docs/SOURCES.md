# 출처·라이선스·검수 기록

## 2026-10-14 E2 임상 커버리지 후보

`meddb/coverage.py`의 추가 문진·연령 맥락·마무리 정책은 팀 작성 초안이며 임상 검수 전입니다. 환자 응답을 대체하거나 특정 샘플의 정답으로 분기하지 않습니다. 아래 문서를 설계 검토에 사용했으며 원문·표·샘플 대본을 추가로 패키징하지 않았습니다.

- VA/DoD 2025 Insomnia/OSA: https://www.healthquality.va.gov/guidelines/CD/insomnia/ — 수면·의학·정신건강·약물 병력 평가.
- FDA benzodiazepine boxed warning: https://www.fda.gov/drugs/drug-safety-and-availability/fda-requiring-boxed-warning-updated-improve-safe-use-benzodiazepine-drug-class — 의존·금단 위험과 급격한 중단 회피.
- Pediatric Endocrine Society: https://pedsendo.org/clinical-resource/child-with-suspected-short-stature/ — 성장 추이·가족·출생·전신 병력 평가.
- NIDDK: https://www.niddk.nih.gov/health-information/endocrine-diseases/graves-disease — 검사 확인 및 임신·수유와 검사/치료 선택.

임상 문서의 내용과 팀 작성 규칙을 승인된 진단 규칙으로 간주하지 않습니다. 질문·설명 문장은 새로 작성했으며 모델의 개별 계획은 추가 임상 검수가 필요합니다.

대회 규정상 외부 데이터·모델·도구는 **연구 출판이 가능한 라이선스만**, **출처를 밝히고** 써야 합니다.
새 자료를 쓰기 전에 이 문서에 먼저 적습니다.

## 1. KB에 들어 있는 것

| 구분 | 파일 | 출처 | 라이선스 |
|---|---|---|---|
| 스키마·코드 | `meddb/*.py`, `tools/*.py` | 팀 자체 작성 | 팀 소유 |
| 온톨로지 내용 | `meddb/data/` 의 JSON 여섯 개 | 팀 자체 작성 (2절) | 팀 소유 |
| KCD 코드·병명 | `meddb/data/kcd.tsv.gz` | 건강보험심사평가원 상병마스터 (3절) | 공공누리 제1유형 |
| 성·연령별 환자수 | `meddb/data/hira_prev.tsv.gz` | 건강보험심사평가원 진료 통계 (3절) | 공공누리 제1유형 |
| 질환–소견 연결 보강 | `meddb/data/ext_ddxplus.json` | DDXPlus (3절) | CC BY 4.0 |
| 진료지침 문서 연결 | `meddb/data/ext_guidelines.json` | N.O.V.A. 2026 진료지침 코퍼스의 목록 (3절) | 서지 정보만 수록, 문서별 라이선스 표기 |

원본 파일 자체는 저장소에 넣지 않고, `tools/`의 도구로 만든 가공 파일만 넣습니다.

## 2. 팀이 쓴 내용

- 2026-10-10 ~ 10-11, AI 코딩 도구(Claude, 모델 설정 `claude-opus-5-5`)로 초안 작성. 대회 규정상 AI 코딩 도구 사용은 허용됩니다.
- 주호소별 감별진단 범위, 위험 질환 지정, 핵심·보조·반대 소견, 질문 문장, 진찰 동작, 검사·처치 계획은
  외부 자료에 없어서 일반 임상 지식으로 직접 썼습니다. 교과서나 진료지침과 대조하지 않았습니다.
- **임상 검수 전입니다.** `common.json`의 `meta.review`를 검수 후 갱신합니다.

## 3. 외부 자료

### 건강보험심사평가원 상병마스터

- 출처: 건강보험심사평가원, 상병마스터 (공공데이터포털 https://www.data.go.kr/data/15067467/fileData.do)
- 기준일 2025-09-30 파일, 2026-10-11 내려받음
- 라이선스: 공공누리 제1유형 (출처표시)
- 가공: 상병기호·한글명·영문명만 발췌, 같은 (코드, 한글명) 중복 제거 → 47,640행
- 쓰임: KB 질환의 KCD 코드 검증 (115개 중 코드가 있는 114개 모두 일치), 진단명 → KCD 코드 조회

### 건강보험심사평가원 주부상병(3단) 성별 연령군별 건강보험 진료 통계

- 출처: 건강보험심사평가원 (공공데이터포털 https://www.data.go.kr/data/15118806/fileData.do)
- 진료년도 2025, 기준일 2025-12-31 파일, 2026-10-11 내려받음
- 라이선스: 공공누리 제1유형 (출처표시)
- 가공: 상병코드·성별·연령군·환자수만 발췌 → 60,490행
- 쓰임: 성·연령별 사전확률 (`MedDB.prior`)
- 한계: KCD 3자리 단위, 진료 환자수 기준이라 실제 발생률과 다름

### DDXPlus

- 출처: Fansi Tchango A, et al. DDXPlus: A New Dataset For Automatic Medical Diagnosis. NeurIPS 2022 Datasets and Benchmarks.
  https://figshare.com/articles/dataset/DDXPlus_Dataset_English_/22687585
- `release_conditions.json`, `release_evidences.json`, 2026-10-11 내려받음
- 라이선스: CC BY 4.0
- 가공: 질환과 문진 항목의 연결만 추출해 KB 소견 id로 옮김. 질환 49개 중 41개, 문진 항목 223개 중 117개 대응
  (`tools/ddxplus_map.json`, 수작업). 질문 문장과 환자 데이터는 가져오지 않음
- 결과: 팀이 쓴 연결과 일치 179건, 새로 들어온 연결 129건(보조 소견으로), 팀 판단과 충돌해 넣지 않은 것 2건
- 한계: 호흡기·흉부 질환 위주의 합성 데이터용 지식이라 가중치가 없고 범위가 좁음

### N.O.V.A. 2026 진료지침 코퍼스

- 출처: 대회 운영진 제공. 문서 15,904개(영어 14,398, 한국어 1,506), 출처 폴더 16곳
- 쓴 것: `catalog.csv`의 서지 정보(파일명, 제목, 발행기관, 연도, 언어, 문서 유형, 라이선스)만. 2026-10-11 받음
- 가공: 제목을 KB의 주호소·질환 이름과 검색어(`tools/guideline_terms.json`)로 찾아 항목당 최대 4개 연결 → 문서 405개
- 쓰지 않은 것: 문서 본문. 저장소에 넣지 않았고 읽지도 않았음. 본문은 실행 환경의 `NOVA_GUIDELINES_DIR`에서 읽음
- 조건: 대회 목적의 비상업적 이용만 허용. 문서를 쓸 때 라이선스와 출처를 함께 표시. 연결된 문서의 다수가
  CC BY-NC-ND · 공공누리 제4유형이라 번역·요약·재구성한 결과물은 배포할 수 없음
- 운영진 확인 대기: ① 코퍼스로 만든 검색 색인·임베딩을 제출 ZIP에 넣어도 되는지, ② 변경 금지 문서에서
  사실(용어·수치)을 뽑아 KB에 쓸 수 있는 범위. 답이 오기 전까지 본문에서 유래한 내용은 KB에 넣지 않음
- 한계: 제목만 보고 고른 연결이라 본문 적합성은 확인되지 않음

## 4. 구조를 참고한 공개 저장소

아래 두 저장소는 설계를 정할 때 읽었습니다. 코드와 데이터 파일은 가져오지 않았습니다.

| 저장소 | 참고한 점 | 비고 |
|---|---|---|
| [yunseul6028/Doctor-Agent](https://github.com/yunseul6028/Doctor-Agent) | KB를 CPU·표준 라이브러리만으로 조회하는 구성, 출처 장부를 두는 방식, 쓸 만한 공개 자료 목록 | 2026-10-10 기준 LICENSE 파일 없음 |
| [BBI-BBO/medagent-kb](https://github.com/BBI-BBO/medagent-kb) | 질환–소견–검사를 관계로 두는 구성, 판 고정 | 2026-10-10 기준 LICENSE 파일 없음 |

두 저장소는 공개되어 있지만 라이선스가 명시되어 있지 않습니다. 코드나 가공 데이터를 직접 넣으려면 저장소 주인에게 이용 조건을 확인한 뒤 이 표에 적습니다.

## 5. 앞으로 넣을 후보 자료

| 자료 | 쓰임 | 라이선스 (재확인 필요) | 배포처 |
|---|---|---|---|
| Human Disease Ontology | 영문 병명·동의어 | CC0 1.0 | DiseaseOntology GitHub |
| Orphadata | 희귀질환 표현형·빈도 | CC BY 4.0 | orphadata.com |
| MedlinePlus Health Topics | 질환별 증상·검사 요약 | 미국 정부 저작물 (제3자 콘텐츠 제외) | medlineplus.gov |

## 6. 검수 체크리스트

- [ ] 주호소별 감별진단 범위와 red flag 지정
- [ ] 질환별 핵심·보조·반대 소견
- [ ] `rule_out` 소견이 실제 배제에 충분한지
- [ ] 계획(검사·치료·처치 결정)과 금기(`unsafe`)
- [ ] 설명 문장(`explain`)의 표현
- [x] KCD 코드 (상병마스터 대조, 검증기가 매번 확인)
- [ ] `tools/ddxplus_map.json`의 문진 항목 대응
- [ ] 활력징후 기준값
- [ ] `ext_guidelines.json`의 문서가 실제로 그 주호소·질환을 다루는지 (본문 확인)
