# 공개 반복 실행 집계

모두 비공식 검토 추정이다. 코드 해시·옵션·증례가 같을 때만 묶었다. 각 조건의 표본 수는 작으며 이미 개발에 사용한 공개 증례다.
동일 로그의 별도 검토 복제는 아래 평균에 포함하지 않는다. 시간은 동시 API 부하에 영향을 받으므로 코드의 속도 효과로 단정하지 않는다.

| 증례 | 버전 | 전체 문맥 | 지침 | 실행/검토 | 평균 추정 (범위) | 평균 입력/출력 | 평균 요청 | 평균 초 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | 0.4.1 | legacy | False | 2/2 | 60.0 (55–65) | 188626/23033 | 25.0 | 475.7 |
| C01 | 0.6.1 | legacy | False | 2/2 | 65.5 (63–68) | 329684/49882 | 46.0 | 1026.3 |
| C01 | 0.7.3 | False | False | 2/2 | 69.5 (67–72) | 228322/43547 | 36.5 | 834.7 |
| C03 | 0.4.1 | legacy | False | 2/2 | 59.0 (55–63) | 190396/23512 | 25.0 | 480.1 |
| C03 | 0.6.1 | legacy | False | 2/2 | 66.5 (66–67) | 241470/33637 | 30.0 | 565.7 |
| C03 | 0.7.3 | False | False | 2/2 | 69.5 (66–73) | 134450/27982 | 23.5 | 494.4 |
| C10 | 0.4.1 | legacy | False | 2/2 | 73.0 (71–75) | 252296/25094 | 31.5 | 507.0 |
| C10 | 0.6.1 | legacy | False | 2/2 | 72.5 (70–75) | 351022/36106 | 37.5 | 599.2 |
| C10 | 0.7.3 | False | False | 2/2 | 73.5 (73–74) | 256476/37304 | 37.5 | 695.4 |

## 코드·조건·실행 근거

- C01 v0.4.1: `85f588178c18713f6dddfb9f3b45246b9042190a774f4c728faeb67868098fb1`; {"closing_turns": null, "compact_context": null, "coverage": null, "final_reasoning_effort": null, "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": null, "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_173555_973870_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_171955_506128_harness`
- C01 v0.6.1: `da08e64bca2884d444e3604a4f234ac05330aa53800255397dd49b92829182c9`; {"closing_turns": 12, "compact_context": null, "coverage": true, "final_reasoning_effort": "medium", "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_170858_455187_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_173650_228844_harness`
- C01 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "compact_context": true, "coverage": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_173522_205116_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_173445_369669_harness`
- C03 v0.4.1: `85f588178c18713f6dddfb9f3b45246b9042190a774f4c728faeb67868098fb1`; {"closing_turns": null, "compact_context": null, "coverage": null, "final_reasoning_effort": null, "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": null, "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_171955_506116_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_172640_334948_harness`
- C03 v0.6.1: `da08e64bca2884d444e3604a4f234ac05330aa53800255397dd49b92829182c9`; {"closing_turns": 12, "compact_context": null, "coverage": true, "final_reasoning_effort": "medium", "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_172741_501004_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_173649_685954_harness`
- C03 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "compact_context": true, "coverage": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_174823_549936_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_173522_725474_harness`
- C10 v0.4.1: `85f588178c18713f6dddfb9f3b45246b9042190a774f4c728faeb67868098fb1`; {"closing_turns": null, "compact_context": null, "coverage": null, "final_reasoning_effort": null, "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": null, "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_173555_973860_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control-v041-hyoxzx98/results/20261018_172640_334936_harness`
- C10 v0.6.1: `da08e64bca2884d444e3604a4f234ac05330aa53800255397dd49b92829182c9`; {"closing_turns": 12, "compact_context": null, "coverage": true, "final_reasoning_effort": "medium", "guidelines": null, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_170859_406968_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/control_v061_007/results/20261018_172503_469055_harness`
- C10 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "compact_context": true, "coverage": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_174824_105704_harness`
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/candidate_v073_007/results/20261018_173446_288361_harness`
