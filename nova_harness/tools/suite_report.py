"""Aggregate repeat runs by case, exact runtime hash, and options; no official score."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01','35dd8b69-2531-454e-bb8c-fb8030293447':'C10','ef3649a9-330b-4e12-ad2d-fab94d019330':'C03'}


def collect(directories):
    groups=defaultdict(list)
    for directory in dict.fromkeys(str(Path(d).resolve()) for d in directories):
        d=Path(directory);m=json.loads((d/'manifest.json').read_text());a=json.loads((d/'analysis.json').read_text())
        review=json.loads((d/'local_review.json').read_text()) if (d/'local_review.json').exists() else None
        version=m.get('agent_version')
        if not version:
            for line in (d/'trace.jsonl').read_text().splitlines():
                row=json.loads(line)
                if row['event']=='consult_start':version=row.get('version');break
        signature=hashlib.sha256(json.dumps(m['fingerprint'],sort_keys=True).encode()).hexdigest()
        options={k:m.get(k) for k in ['max_turns','meddb','coverage','structured_closing','closing_turns','compact_context','guidelines','planner_reasoning_effort','final_reasoning_effort']}
        key=(CASES.get(m['case_id'],'unknown'),version,signature,json.dumps(options,sort_keys=True))
        groups[key].append({'directory':str(d),'manifest':m,'analysis':a,'review':review})
    return groups


def summarize(groups):
    output=[]
    for (case,version,signature,options),runs in sorted(groups.items()):
        scores=[r['review']['estimated_total'] for r in runs if r['review']]
        output.append({'case':case,'version':version,'source_sha256':signature,'options':json.loads(options),
                       'runs':len(runs),'completed':sum(bool(r['analysis']['completed']) for r in runs),'reviewed':len(scores),
                       'mean_estimate':mean(scores) if scores else None,'range':[min(scores),max(scores)] if scores else None,
                       'mean_input':mean(r['analysis']['prompt_tokens'] for r in runs),
                       'mean_output':mean(r['analysis']['completion_tokens'] for r in runs),
                       'mean_attempts':mean(r['analysis']['doctor_attempted_request_ids'] for r in runs),
                       'mean_seconds':mean(r['analysis']['elapsed_seconds'] for r in runs),
                       'areas':{k:mean(r['review']['scores'][k]['score'] for r in runs if r['review']) for k in runs[0]['review']['scores']} if all(r['review'] for r in runs) else {},
                       'directories':[r['directory'] for r in runs]})
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+');p.add_argument('--output',required=True);args=p.parse_args()
    summaries=summarize(collect(args.runs))
    lines=['# 공개 반복 실행 집계','',
           '모두 비공식 검토 추정이다. 코드 해시·옵션·증례가 같을 때만 묶었다. 각 조건의 표본 수는 작으며 이미 개발에 사용한 공개 증례다.',
           '동일 로그의 별도 검토 복제는 아래 평균에 포함하지 않는다. 시간은 동시 API 부하에 영향을 받으므로 코드의 속도 효과로 단정하지 않는다.','',
           '| 증례 | 버전 | 전체 문맥 | 지침 | 실행/검토 | 평균 추정 (범위) | 평균 입력/출력 | 평균 요청 | 평균 초 |',
           '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for s in summaries:
        opt=s['options'];score='미검토' if s['mean_estimate'] is None else f"{s['mean_estimate']:.1f} ({s['range'][0]}–{s['range'][1]})"
        context='legacy' if opt['compact_context'] is None else str(not opt['compact_context'])
        lines.append(f"| {s['case']} | {s['version']} | {context} | {bool(opt['guidelines'])} | {s['runs']}/{s['reviewed']} | {score} | {s['mean_input']:.0f}/{s['mean_output']:.0f} | {s['mean_attempts']:.1f} | {s['mean_seconds']:.1f} |")
    lines+=['','## 코드·조건·실행 근거','']
    for s in summaries:
        lines+=['- '+s['case']+' v'+str(s['version'])+': `'+s['source_sha256']+'`; '+json.dumps(s['options'],ensure_ascii=False)]
        lines+=['  - `'+d+'`' for d in s['directories']]
    Path(args.output).write_text('\n'.join(lines)+'\n')
    dest=Path('results/suite_report_007.json');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n')
    print(Path(args.output).resolve())

if __name__=='__main__':main()
