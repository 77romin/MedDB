# 58차: B1O1 사용자 제출 파일

사용자 요청으로 최신 main 기반 관찰 개선 후보를 별도 ZIP으로 생성했다. 기본 B1·이전 Q1을 바꾸거나 공식 업로드·PR 병합을 수행하지 않는다.

- 파일: dist/submission_B1O1_observation.zip
- 16,017,348바이트,54파일,50MB 한도 이하
- SHA256: cb5155eeb5cb46de49417b5b983c7dc6b7a3a60b95696132e2ecf87d1f0a10db
- 기준 main: 05f9ed09ae49c0ecbf79e9af091a74fad1a658a1
- 검증한 런타임: 734d0d6

기존 B1 패키저를 재사용하는 make_b1_observed_submission.py로 생성했다. 진입점은 agent_b1_observed이며29턴 문진·기존 선택/기록/마무리를 유지하고 추가 모델 추출/RAG는 포함하지 않는다.

ZIP 무결성·전체 Python 구문·로컬 개발 키 바이트 및 개발 문서/로그 제외를 확인했다. 포함된5개 핵심 모듈 SHA256이57차 최종 API 지문과 같다. 압축 해제한 독립 환경에서 C01/C03/C10 저장 세션의 모델 입력·행동·최종SOAP가 전부 일치했다. 저장된 진찰 거절/제공자 오류도 재발생시켰다. 일부러 최종 SOAP를 변경한 로그는 검증 실패로 거절됐다. 기존 B1의 예외 fallback이 검증 불일치를 삼키지 않도록 재생 오류는 별도 BaseException으로 처리했다.

새 API·Docker·공식 환경·점수 검증은 아니다.57차 main143테스트(4skip), 기존331테스트, 후보3개 API 검증 범위를 승계한다. 실제 단순 예/아니요 연결 분기0회·진찰 거절·제공자 오류·정규식 해석 한계가 남으며 공식 점수 향상을 확정하지 않는다.

집계와 식별 정보는 submission_b1o1_replay_058.json 및 submission_b1o1_manifest_058.json에 기록한다. 원문 실행 로그·키·ZIP은 Git에 올리지 않는다.
