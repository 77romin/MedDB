# 공개 반복 실행 집계

모두 비공식 검토 추정이다. 코드 해시·옵션·증례가 같을 때만 묶었다. 각 조건의 표본 수는 작으며 이미 개발에 사용한 공개 증례다.
동일 로그의 별도 검토 복제는 아래 평균에 포함하지 않는다. 시간은 동시 API 부하에 영향을 받으므로 코드의 속도 효과로 단정하지 않는다.

| 증례 | 버전 | 전체 문맥 | 지침 | 실행/검토 | 평균 추정 (범위) | 평균 입력/출력 | 평균 요청 | 평균 초 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | 0.7.3 | False | False | 1/1 | 61.0 (61–61) | 159482/33039 | 30.0 | 641.7 |
| C01 | 0.8.0 | False | False | 1/1 | 70.0 (70–70) | 266726/41176 | 40.0 | 695.3 |
| C01 | 0.8.0.1 | False | False | 1/1 | 68.0 (68–68) | 317592/59578 | 45.0 | 1144.7 |
| C01 | 0.8.1 | False | False | 1/1 | 66.0 (66–66) | 325451/61043 | 44.0 | 1051.8 |
| C01 | 0.8.2 | False | False | 1/1 | 66.0 (66–66) | 348163/62685 | 49.0 | 1292.3 |
| C01 | 0.8.3 | False | False | 1/1 | 66.0 (66–66) | 375960/70801 | 51.0 | 1132.2 |
| C03 | 0.7.3 | False | False | 1/1 | 69.0 (69–69) | 161468/35034 | 31.0 | 687.0 |
| C03 | 0.8.0 | False | False | 1/1 | 68.0 (68–68) | 134994/27559 | 24.0 | 434.0 |
| C03 | 0.8.0.1 | False | False | 1/1 | 71.0 (71–71) | 176615/30588 | 28.0 | 595.3 |
| C03 | 0.8.1 | False | False | 1/1 | 71.0 (71–71) | 162209/31317 | 25.0 | 519.3 |
| C03 | 0.8.2 | False | False | 1/1 | 72.0 (72–72) | 194785/39220 | 31.0 | 793.6 |
| C03 | 0.8.3 | False | False | 1/1 | 66.0 (66–66) | 204420/39459 | 31.0 | 659.9 |
| C10 | 0.7.3 | False | False | 1/1 | 78.0 (78–78) | 223340/31546 | 33.0 | 562.1 |
| C10 | 0.8.0 | False | False | 1/1 | 74.0 (74–74) | 237854/33587 | 34.0 | 565.8 |
| C10 | 0.8.0.1 | False | False | 1/1 | 79.0 (79–79) | 264414/40729 | 36.0 | 731.2 |
| C10 | 0.8.1 | False | False | 1/1 | 76.0 (76–76) | 229256/35180 | 30.0 | 598.3 |
| C10 | 0.8.2 | False | False | 1/1 | 73.0 (73–73) | 307479/48320 | 40.0 | 885.9 |
| C10 | 0.8.3 | False | False | 1/1 | 75.0 (75–75) | 325237/55624 | 42.0 | 860.6 |

## 코드·조건·실행 근거

- C01 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": null, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_control_v073_009/results/20261018_183146_809319_harness`
- C01 v0.8.0: `4bec344b36beac1ff05f52c0969604d6280a7df04b223814247a43e3252349dc`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v080_009/results/20261018_183341_896265_harness`
- C01 v0.8.0.1: `e839fc2e3a6a8a4976f5cc14b686018a7a36dd0e5d75b4753edcebfd81f1e12c`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v0801_009/results/20261018_184518_639876_harness`
- C01 v0.8.1: `a34571553cf4093ff1aa95824dd7015493e4a2f3366783a5b7991a63d65d2bf5`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_closing_v081_009/results/20261018_184551_708445_harness`
- C01 v0.8.2: `a9478ea6d6011aa0213a5a50d3fd6f0222ace2efd366077c6403e3d17b7acf22`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_records_v082_009/results/20261018_185554_539305_harness`
- C01 v0.8.3: `fc76e8689351031f030359e0a8213f64d4c656441a2538865d9127002d6043bd`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_recovery_v083_009/results/20261018_192150_713725_harness`
- C03 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": null, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_control_v073_009/results/20261018_183145_786873_harness`
- C03 v0.8.0: `4bec344b36beac1ff05f52c0969604d6280a7df04b223814247a43e3252349dc`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v080_009/results/20261018_183342_926450_harness`
- C03 v0.8.0.1: `e839fc2e3a6a8a4976f5cc14b686018a7a36dd0e5d75b4753edcebfd81f1e12c`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v0801_009/results/20261018_184519_668602_harness`
- C03 v0.8.1: `a34571553cf4093ff1aa95824dd7015493e4a2f3366783a5b7991a63d65d2bf5`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_closing_v081_009/results/20261018_184552_240213_harness`
- C03 v0.8.2: `a9478ea6d6011aa0213a5a50d3fd6f0222ace2efd366077c6403e3d17b7acf22`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_records_v082_009/results/20261018_185554_010846_harness`
- C03 v0.8.3: `fc76e8689351031f030359e0a8213f64d4c656441a2538865d9127002d6043bd`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_recovery_v083_009/results/20261018_192150_174775_harness`
- C10 v0.7.3: `104165614bf339819e84e0068b3187749742f1bff84e4476f27a808836689577`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": null, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_control_v073_009/results/20261018_183146_326351_harness`
- C10 v0.8.0: `4bec344b36beac1ff05f52c0969604d6280a7df04b223814247a43e3252349dc`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v080_009/results/20261018_183342_425093_harness`
- C10 v0.8.0.1: `e839fc2e3a6a8a4976f5cc14b686018a7a36dd0e5d75b4753edcebfd81f1e12c`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_goals_v0801_009/results/20261018_184519_168412_harness`
- C10 v0.8.1: `a34571553cf4093ff1aa95824dd7015493e4a2f3366783a5b7991a63d65d2bf5`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_closing_v081_009/results/20261018_184552_751211_harness`
- C10 v0.8.2: `a9478ea6d6011aa0213a5a50d3fd6f0222ace2efd366077c6403e3d17b7acf22`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_records_v082_009/results/20261018_185555_037719_harness`
- C10 v0.8.3: `fc76e8689351031f030359e0a8213f64d4c656441a2538865d9127002d6043bd`; {"closing_turns": 12, "closure_audit": false, "compact_context": true, "coverage": true, "decision_review": true, "final_reasoning_effort": "medium", "guidelines": false, "max_turns": 45, "meddb": true, "planner_reasoning_effort": "medium", "structured_closing": true}
  - `/Users/mink/Documents/ChatGPT/NOVA medic Agent/results/stage_recovery_v083_009/results/20261018_192151_226300_harness`
