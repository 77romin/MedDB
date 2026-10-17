"""Aggregate explicit run directories by public case; local estimates remain separate."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nova_agent.analysis import write_report

CASES = {'4fa07144-04e5-4116-a18e-88d8a90cc21a': 'C01',
         '35dd8b69-2531-454e-bb8c-fb8030293447': 'C10',
         'ef3649a9-330b-4e12-ad2d-fab94d019330': 'C03'}


def build(paths):
    runs = []
    for path in paths:
        directory = Path(path).resolve()
        manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        summary = write_report(directory/'trace.jsonl')
        review_path = directory/'local_review.json'
        review = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else None
        runs.append({'case': CASES.get(manifest['case_id'], manifest['case_id']), 'manifest': manifest,
                     'directory': str(directory), 'summary': summary, 'review': review})
    lines = ['# 공개 샘플 벤치마크', '',
             '실험별 1회 실행. 공식 점수·일반화 성능·실제 청구 비용을 의미하지 않는다.', '',
             'C01은 개발 과정에서 반복적으로 확인한 증례이며 독립 검증 증례가 아니다. '
             '자가평가 점수는 동일 개발용 평가 모델의 비공식 추정이고 검토자 변동도 통제하지 않았다.', '']
    for case in sorted({r['case'] for r in runs}):
        lines += ['## '+case, '',
                  '| 버전 | 턴 상한 | 완료 | 턴 | Doctor 요청 | 입력/출력 토큰 | 시간(초) | JSON 잘림 | 종료 원인 | 자가평가 |',
                  '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
        for run in (r for r in runs if r['case'] == case):
            s, m, review = run['summary'], run['manifest'], run['review']
            values = [m.get('label') or m['agent'], m.get('max_turns', '미기록'), s['completed'], s['max_server_turn'],
                      s['doctor_attempted_request_ids'], f"{s['prompt_tokens']}/{s['completion_tokens']}",
                      s['elapsed_seconds'], s['truncated_completions'], s['collection_stop_reason'] or 'baseline/unknown',
                      str(review['estimated_total'])+'/100' if review else '미실행']
            lines.append('| '+' | '.join(str(x).replace('|', '\\|').replace('\n', ' ') for x in values)+' |')
        lines += ['', '주진단과 주요 검토 결과:', '']
        for run in (r for r in runs if r['case'] == case):
            s, m, review = run['summary'], run['manifest'], run['review']
            lines.append('- **'+(m.get('label') or m['agent'])+'**: '+str(s['diagnosis']))
            if review:
                lines.append('  - 검토 모델 판정: '+str(review.get('diagnosis_assessment', {}).get('match', 'unknown')))
                lines.extend('  - '+str(fix) for fix in review.get('priority_fixes', [])[:3])
        lines.append('')
    lines += ['## 실행 조건', '',
              '원본 E2와 E2 확장 후보는 원본의 수집 최대 36턴+마무리, 서버 최대 50턴 정책을 사용한다. '
              '통합 harness는 지정된 전체 턴 상한에서 마무리 8턴을 예약한다. '
              '정책이 다른 결과는 개별 구성요소의 효과를 분리한 비교가 아니다.', '']
    for run in runs:
        m = run['manifest']
        lines.append('- '+(m.get('label') or m['agent'])+': `'+Path(run['directory']).name+'`')
    lines.append('')
    lines += ['## 로그와 재현', '',
              '각 실행 폴더의 manifest.json·source_snapshot.zip·trace.jsonl·analysis.json·local_review.json을 함께 보관한다. '
              '개발 키와 공개 정답은 제출 ZIP에 들어가지 않는다.', '']
    return {'runs': runs, 'scope': 'public-development-only'}, '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+')
    p.add_argument('--output', default='reports/benchmark_002.md')
    args = p.parse_args()
    data, markdown = build(args.runs)
    dest = Path(args.output); dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(markdown, encoding='utf-8')
    # JSON includes local clinical traces indirectly through review: keep it under ignored results.
    out = ROOT/'results/benchmark_report.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(dest.resolve())


if __name__ == '__main__': main()
