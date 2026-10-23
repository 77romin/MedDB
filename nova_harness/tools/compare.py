"""Compare local runs without inventing official clinical scores."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nova_agent.analysis import write_report


def compare(paths):
    runs = []
    for path in paths:
        trace = Path(path)
        if trace.is_dir(): trace = trace/'trace.jsonl'
        manifest = json.loads(trace.with_name('manifest.json').read_text(encoding='utf-8'))
        result = write_report(trace)
        runs.append({'directory': str(trace.parent), 'manifest': manifest, 'result': result})
    comparable = len({(x['manifest']['case_id'], x['manifest']['max_turns'], x['manifest']['model']) for x in runs}) == 1
    lines = ['# 개발 샘플 실행 비교', '',
             '같은 증례·턴 상한·Doctor: '+str(comparable), '',
             '공식 점수나 임상 정확도를 이 표로 판정하지 않습니다. 단일 실행이고 가상 환자 응답도 달라질 수 있습니다.', '',
             '| 실행 | 제출 완료 | 서버 턴 | Doctor 요청 | 입력 토큰 | 출력 토큰 | 시간(초) | 주진단 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for x in runs:
        r = x['result']; m = x['manifest']
        cells = [m.get('label') or m['agent'], r['completed'], r['max_server_turn'],
                 r['doctor_attempted_request_ids'], r['prompt_tokens'], r['completion_tokens'], r['elapsed_seconds'], r['diagnosis']]
        lines.append('| '+' | '.join(str(v).replace('|', '\\|').replace('\n', ' ') for v in cells)+' |')
    return {'same_case_turn_limit_model': comparable, 'runs': runs}, '\n'.join(lines)+'\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+')
    p.add_argument('--output', default='results/comparison.md')
    a = p.parse_args()
    result, markdown = compare(a.runs)
    target = Path(a.output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding='utf-8')
    target.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(markdown)


if __name__ == '__main__': main()
