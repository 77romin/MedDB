# NOVA Doctor Agent

예선 고정 Doctor `openai/gpt-6-luna`를 사용하는 표준 라이브러리 기반 개발 하네스다. 설계 자료는 [자료 목차](nova_reference/README.md), 상세 계획은 [구현계획](nova_reference/08_implementation_plan.md)에 있다.

기존 프로젝트의 점수 정체를 해결하기 위해 새로 개발하는 독립 프로젝트다. MedDB 저장소의 `codex/nova-harness-rebuild` 브랜치에서 `nova_harness/`에 보관하며, 아래 명령은 이 디렉터리 안에서 실행한다. [의사결정 기록](DECISIONS.md)에 사용자 의도·고민·실험의 채택 이유를 대화마다 갱신한다. 공식 목표는 **≥78 → ≥85 → ≥90점**이다. 사용자의 변경 요청으로 목표 달성 전 [PR #5](https://github.com/SSAFY16-S11-NOVA2026/MedDB/pull/5)를 열어 개발을 이어간다. [저장소 전달 기록](docs/REPOSITORY_HANDOFF.md)에서 커밋 구분과 복원 방법을 확인할 수 있다.

실제 개발 API 실행·원인 분석·수정 이력은 [개발 1차 보고서](reports/development_001.md)에 정리했다. 현재는 실험용 초기 버전이다.

공개 샘플 확장과 종료 검토의 채택 결정은 [개발 2차 보고서](reports/development_002.md), 증례별 수치는 [벤치마크](reports/benchmark_002.md)에 있다. 현재 하네스의 전반적 우수성은 확인되지 않았다.

최신 [5차 보고서](reports/development_005.md)와 [10회 비교](reports/benchmark_005.md)는 새 기준 67/77, v0.5.2 66/76, low 문진 62/74의 비공식 추정을 기록한다. 전체 점수 향상은 확인되지 않았다. 5차 최종 v0.6.1은 근거 범위 검사·수집 상태·동반 증상 연결과 502/503/504 전송 복구를 포함한다. 최종 버전 테스트 94개 통과와 전체 API 미재측정을 구분한다.

점수 정체의 코드·로그 근거와 다음 승인 범위는 [6차 심층 분석·계획](reports/analysis_plan_006.md)에 있다. 사용자 승인 후 [7차 개발·비교](reports/development_007.md)를 완료했다. v0.7.3의 [18회 반복 집계](reports/repeated_007.md)와 [26회 전체 결과](reports/benchmark_007.md)를 함께 확인한다. 작은 비공식 평균 차이를 공식 성능 향상으로 해석하지 않는다.

버전별 실제 문진·진찰·설명·기록의 실패 경로와 다음 개발 우선순위는 [8차 로그 비교·개선안](reports/log_comparison_008.md)에 있다. 해당 회차는 분석만 수행했다. 후속 승인에 따른 단계별 구현·실험 진행은 [9차 개발 보고](reports/development_009.md)에 기록한다.

E2 원본 복구 후 첫 단일 변경 실험은 [15차 개발 보고](reports/development_015.md)에 기록한다. 실제 C01 로그의 질문 미답변만 수정한 실험 후보가 있으며, 개발 API 비교 전에는 제출을 권장하지 않는다. v0.9.7은 61.559점, E2는 77.714점, E2 보정본은 74.690점이었다. 안전·소통이 하락한 보정본은 폐기하고 원본 E2를 복구 기준으로 고정한다.

외부 공개 프로젝트 비교와 C01 약물 재확인 실험은 [16차 개발 보고](reports/development_016.md)에 기록한다. 약물 재확인은 비공식 64→66이었으나 단일 실행 변동 범위라 채택하지 않았다. 실제 안전 안내를 결합한 다음 후보는 테스트만 완료했으며 개발 API 검증 전에는 제출을 권장하지 않는다.

후속 약물 안전 후보의 [17차 API 검증](reports/development_017.md)은 비공식 65점이었다. 안전 문장은 전송됐지만 안전 점수는 유지되고 효율이 하락했으며 환자 질문 답변은 실패했다. 후보를 폐기하고 C03/C10으로 확장하지 않는다.

턴 재배정 후보는 C01에서 반복 질문을 줄이고 감독하 감량·추적·응급·CBT-I를 실제 전달해 비공식 75점을 기록했다. 단일 공개 증례 결과이므로 제출 후보가 아니며 C03·C10 회귀 검증이 남아 있다.

해당 제출본의 공식 샘플 검증은 69.759점으로 원본 E2보다 낮았다. 전역 `P.education` 덮어쓰기가 안전·검사·소통을 함께 훼손한 유력 원인이라 제거했으며, 수정본은 다시 3증례를 검증하기 전까지 제출하지 않는다. 자세한 내용은 [19차 보고](reports/development_019.md)에 있다.

반복 대화에서 초기 근거가 SOAP에서 누락되는 문제는 [20차 Evidence Ledger 구현 계획](reports/implementation_plan_020.md)으로 다룬다. 원본 E2 행동을 유지한 채 모든 성공 SAY/EXAM을 불변 원장에 기록하고, 제출 직전 각 근거의 반영 또는 제외 사유를 감사하는 별도 실험이다.

## 현재 구현 범위

MedDB 적용 내용과 후보 비교는 [3차 보고서](reports/meddb_review_003.md), [MedDB 벤치마크](reports/meddb_benchmark_003.md)에 있다. 공식 67.132점과 개발용 자가평가를 구분한다.

PR 생성 후 다중 문장 설명·환자 질문 응답·교육 기록 분리는 [4차 보고서](reports/development_004.md), [비교 표](reports/benchmark_004.md)에 정리한다. 최종 v0.4.1은 불완전한 연결절을 거절하고 종료 자체도 최대 12턴으로 제한한다. v0.4.0 개발 API 결과와 후속 v0.4.1의 단위 검증을 구분하며, 공식 제출 후보로 채택하지 않았다.

- `run.py`: 공식 `prepare → ready → consult → diagnose` 진입점.
- `nova_agent/protocol.py`: SDK 래퍼, 같은 작업 ID 재시도와 무효 응답 새 ID 재시도, 시간·호출·토큰 예산.
- `nova_agent/state.py`: 환자별 원문 증거와 턴, 모델 추출 사실의 출처·부정·주체·시간 상태.
- `nova_agent/ontology.json`: 초진 정보 구조 시드. MedDB 임상 관계는 `clinical_graph.json`에 별도 보관하며 검수 전 초안이다.
- `nova_agent/coverage.py`: 그래프 기반 미질문·미해결·상충·진찰 획득 구분, 제한된 동반 증상 연결. `--no-coverage`로 제거 비교한다. 의미 매핑의 임상 검증은 남아 있다.
- `nova_agent/clinical.py`: MedDB의 주호소·감별 관계에서 다음 행동을 제안한다. `--no-meddb`로 제거 실험할 수 있다.
- `nova_agent/closing.py`: 개인별 설명을 여러 완결 문장으로 나누고, 중간 환자 질문·구체적 두려움에 최대 3회 답변 생성, 이해 확인 후 한 번 오해 교정을 수행한다. 각 SAY는 30자 제한을 지킨다.
- `nova_agent/meddb_overlay.py`: 원본 E2 문진·진단을 유지하는 별도 확장. 원본 파일을 수정하지 않고 복용 내역 확인과 설명만 보완한다.
- `nova_agent/runtime.py`, `prompts.py`: 사실 갱신·다음 행동 선택·설명·최종 판단 흐름.
- `nova_agent/closure.py`: 종료 직전 한 번만 중요한 누락 검토. 긴급 종료·시간/턴 부족·검토 실패 시 추가 질문을 강제하지 않는다. 현재 기본 비활성화이며 `--closure-audit`로 선택적 실험 가능.
- `nova_agent/records.py`: S/O를 실제 응답으로 구성하고 P.education의 교육 계획과 실제 성공한 SAY를 출처 ID·턴으로 구분한다. 태그가 설명 내용의 임상 충분성을 증명하지는 않는다.
- `nova_agent/telemetry.py`, `analysis.py`: 인증정보를 제외한 JSONL 로그와 실행 분석. 임상 정확도·공식 점수는 자동 판정하지 않는다.
- `tools/experiment.py`: 공식 원본 baseline 또는 하네스를 공개 개발 샘플로 실행. 리더보드 제출 기능은 없다.

원문 일치 검증은 모델이 추출한 의미·부정·시간의 정확성을 보증하지 않는다. 현재 사실 매핑과 임상 판단은 아직 검토 대상이다. S/O는 출처 보존을 우선한 초안 형식이다. 질환 관계의 임상 검수, 독립 검증 세트, 정교한 임상 기록 문장화는 다음 단계다.

## 실행

Python 3.12를 권장한다. 다운로드한 SDK는 1.0.1이며 원본을 수정하지 않았다. 첫 복원 시:

```sh
python3 tools/bootstrap.py
python3 -m unittest discover -s tests -v
```

프로젝트 `.env`에 로컬 개발 키를 설정한다. 실행 도구만 `.env`를 읽으며 제출 진입점은 읽지 않는다. `.env`는 Git·제출 ZIP에서 제외된다. 키 내용은 공유하지 않는다.

```text
NOVA_API_BASE=https://nova.snubhai.org
NOVA_DEV_KEY=발급받은_개인_개발키
```

```sh
python3 tools/experiment.py check
python3 tools/experiment.py list
python3 tools/experiment.py run --case 공개_UUID --agent baseline --max-turns 30
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 30
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 30 --no-closure-audit
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 30 --closure-audit
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 45 --no-meddb --no-structured-closing
python3 tools/experiment.py run --case 공개_UUID --agent meddb_e2
python3 tools/experiment.py run --case 공개_UUID --agent meddb_e2_plus
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 45 --planner-effort low
python3 tools/experiment.py analyze results/실험폴더/trace.jsonl
python3 tools/compare.py results/기준실행 results/하네스실행
python3 tools/package_submission.py
```

`list`는 공개 증례와 운영진이 공개한 정답 메타데이터를 보여 줄 수 있다. 이를 Planner 입력으로 사용하지 않는다. 런타임은 공개 대본·모범 기록·정답 파일을 읽지 않는다. 키는 공식 HTTPS origin에만 전송한다. `run`은 개발 크레딧과 샘플 생성 횟수를 사용하며, 진료 실행 자체는 공식 채점이 아니다.

완료된 공개 샘플 실행은 세션 밖 개발용 `openai/gpt-6.1-sol`로 별도 검토할 수 있다. 이 명령도 개발 크레딧을 사용하며 `local_review.json`의 점수는 공식 점수와 다르다. 공개 비교 대본·모범 기록은 이 평가 도구만 읽고 진료 에이전트에는 전달하지 않는다.

MedDB 비교 실행에는 `vendor/meddb`에 고정 커밋의 저장소가 필요하다. `meddb_e2`와 `meddb_e2_plus`는 원본의 최대 36턴 수집+마무리·서버 최대 50턴 정책을 유지하며 `--max-turns`로 덮어쓰지 않는다. 이 정책은 manifest에 명시된다. 현재 harness의 문진 추론은 기본 medium이며 `--planner-effort low`로 계산량 비교를 할 수 있다. 최종 판단·종료 설명은 medium을 유지한다. low의 전체 점수 향상은 확인되지 않았다. harness는 지정 상한에서 마무리 12턴을 예약한다(이전 8턴). v0.4.1부터 실제 마무리도 12턴으로 제한한다. 충분한 문진·진찰을 위한 턴과 설명 턴의 균형은 계속 측정한다.

새 환경에서 MedDB 비교본과 ZIP을 복원할 때는 다음 순서로 고정 커밋을 준비한다. 이미 있는 checkout에는 `git clone`을 다시 실행하지 않는다.

```sh
git clone https://github.com/SSAFY16-S11-NOVA2026/MedDB.git vendor/meddb
git -C vendor/meddb checkout 63743a8b8a2e278b426d18fc040e880740318ae3
python3 tools/import_meddb.py
python3 vendor/meddb/tools/make_submission.py --starter vendor/starter/run.py --agent hybrid_care --knowledge-mode clinical --reference-profile reviewed --out dist/submission_meddb_E2_reference.zip
python3 tools/package_meddb_plus.py
```

```sh
python3 tools/judge.py results/완료된실험 --public-case C01
```

## 실험 결과

각 실행을 `results/KST시각_에이전트/`에 저장한다.

| 파일 | 내용 |
| --- | --- |
| `manifest.json` | 증례·모델·버전별 파일 해시·실험 조건 |
| `source_snapshot.zip` | 실험 시작 당시의 허용된 코드 파일 사본. 키·샘플 정답 제외 |
| `trace.jsonl` | 요청·응답·오류·재시도·선택 목적·사실 갱신·제출 |
| `analysis.json` | 성공 여부·요청 수·토큰·시간·문제 분류 |
| `analysis.md` | 분석 요약과 다음 점검 항목 |
| `local_review.json` | 선택적 개발용 평가 모델의 비공식 영역별 추정·문제 인용 |

`judge_trace.jsonl`에는 개발용 평가자의 입력·출력·사용량을 별도로 보관한다. 같은 실행을 다시 검토할 때는 저장된 결과를 재사용하며 추가 유료 검토는 `--force`로 명시한다.

인증정보를 가려도 임상 대화 자체는 로그에 남는다. 현재 공개 가상환자용이며 실제 환자 데이터 운영을 위한 접근통제·보존정책을 구현한 제품은 아니다. 실험 로그는 Git·제출 자산에서 제외하고 실행마다 상태를 초기화한다.

비교는 같은 증례·턴 상한·Doctor로 수행하되 단일 실행의 우열을 일반화하지 않는다. baseline은 공식 파일을 그대로 불러오며 `MAX_TURNS`만 실험 조건으로 설정한다. baseline과 하네스의 재시도·종료 여유·프롬프트는 다르므로 전체 시스템 비교이며 개별 기능의 인과 효과를 의미하지 않는다.

선택적 종료 검토는 충분한 시간과 7턴 이상의 여유가 있고 응답 증거가 5개 이상일 때 첫 DONE에 한 번만 적용한다. 검토자는 최대 3개 누락과 다음 행동 하나를 제안한다. 중요한 누락이 없거나 긴급 처치를 지연할 경우 종료하며, 검토 실패도 제출을 막지 않는다. v0.2.0의 C01 실행에서 개선이 관찰되지 않아 v0.2.1은 이 기능을 기본 비활성화했다. 다중 공개 증례 결과는 `tools/benchmark_report.py`로 합칠 수 있다.

## 7차 후보의 비교 옵션

v0.7.3은 미질문 큐로 자유 질문을 강제 교체하지 않고, 정량·시간 속성의 원문과 진찰 재평가 출처를 검사한다. 종료 설명은 계획·추적을 반복 판단보다 앞서 전달한다. 실제 의미·임상 충분성은 별도 검토가 필요하다. 테스트 통과를 공식 성능으로 해석하지 않는다.

```sh
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 45
python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 45 --full-context
python3 tools/fetch_guidelines.py
NOVA_GUIDELINES_DIR="$PWD/vendor/guidelines/guidelines" python3 tools/experiment.py run --case 공개_UUID --agent harness --max-turns 45 --guidelines
python3 tools/judge.py results/완료된실험 --public-case C01 --review-tag calibration
```

지침은 기본 비활성화다. 공식 서버에서는 제공된 `NOVA_GUIDELINES_DIR`를 읽으며 실행 중 내려받지 않는다. 로컬 복원은 공개 해시를 확인한다. 코퍼스·원문 발췌는 Git·제출 ZIP에서 제외한다. `tools/run_suite.py`는 `results/` 아래 고정 소스의 한정된 실행 계획을 재개하며 키 파일을 복사하지 않는다. `tools/development_review.py`는 세션 밖 개발 모델로 합성 추출 반례를 생성한다. 반례의 의미·라벨은 검토가 필요하며 대회 증례나 임상 검증 데이터가 아니다.

## 9차 단계별 개선

`goals.py`는 이번 환자의 결정 목표·원문 근거·대상/시간 범위를 추적한다. v0.8.3은 활성 목표 최대 8개와 완료 이력을 분리하고, 프롬프트에는 활성 목표와 최근 완료·유보 4개를 제공한다. 일반 DONE 전 한 번만 중요한 누락을 검토하며, 즉시 필요한 안전 행동은 수집 중에도 전달할 수 있다. `--no-decision-review`는 이 목표·종료 검토를 제거하는 실험 옵션이다.

상담은 새 질문·구체적 두려움을 추적하며, 형식 검증에 실패한 답은 같은 질문에 한 번 다시 생성할 수 있다. 전체 답변 호출은 최대 3회이고 필수 다음 행동·시점·안전 안내 예산을 보호한다. 답변 ID가 연결됐다는 사실은 의미 충족·환자 이해의 검증이 아니다.

`history.py`는 실제 SAY 응답 ID로 병력을 분류하고 전체 응답을 보존한다. 같은 응답의 fact 메타데이터 반복을 줄이며, 이해 확인은 교육 기록으로 옮긴다. 자유 문장 임상 요약의 정확성을 보증하는 기능은 아니다.

[9차 보고](reports/development_009.md), [단계별 모니터](reports/staged_009.md), [실험 소스 재구성](reports/reproducibility_009.md)에서 점수·실패·한계를 함께 확인한다. 첫 15회에서는 일관된 점수 상승이 없었다. 실제 결함을 고친 3회를 추가해 총 18회 진료·18회 기본 검토·동일 로그 복제 1회를 완료했다. 최종 v0.8.3은 66/66/75의 비공식 추정이며 일관된 점수 상승을 확인하지 못했다. 제출 권장 후보 승격은 보류한다. 새 공식 점수는 미측정이며 자동 제출하지 않는다.

## 제출·환경 확인

`tools/package_submission.py`는 진입점·SDK·requirements, `nova_agent`의 Python/JSON, `third_party/meddb`의 출처·통지를 포함한다. 개발 키·공개 정답·vendor·결과·테스트·도구는 제외한다. ZIP을 자동 업로드하지 않는다. E2 확장 후보는 `tools/package_meddb_plus.py`로 별도 생성한다.

`local.Dockerfile`은 공식 파일이다. 실제 환경 확인은 제출 ZIP을 별도 폴더에 풀어 그 폴더만 Docker build context로 사용한다. 개발 폴더 전체로 이미지를 만들면 `.env`가 복사될 수 있으므로 `.dockerignore`도 함께 제공한다.

```sh
docker build -f local.Dockerfile -t nova-agent .
docker run --rm --network=none --read-only --tmpfs /tmp nova-agent \
  python -c "from run import prepare; prepare(); print('prepare OK')"
```

Docker 실행과 실제 서버 샘플 검증을 통과하기 전에는 서버 환경 재현 검증을 완료했다고 간주하지 않는다.
