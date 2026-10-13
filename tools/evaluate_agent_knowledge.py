"""Offline ranking comparisons and optional three-arm real-agent log evaluation."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB
from meddb.workflow import resource

ROOT=Path(__file__).resolve().parents[1]


def legacy(kb,obs):
    grouped={}
    for a in kb.assertions(True):
        if a['predicate']=='has_phenotype':grouped.setdefault(a['subject'],set()).add(a['object'])
    result=[]
    for d,findings in grouped.items():
        yes=sum(s=='present' and f in findings for f,s in obs.items())
        no=sum(s=='absent' and f in findings for f,s in obs.items())
        if yes:result.append((d,yes,no))
    return [d for d,_,_ in sorted(result,key=lambda r:(-r[1],r[2],r[0]))]


def evaluate_logs(path):
    """Input records need independently adjudicated correctness and exact arm names."""
    rows=json.loads(Path(path).read_text(encoding='utf-8'))
    groups={arm:[] for arm in ('no_kb','previous_kb','improved_kb')}
    for row in rows:
        if row.get('arm') not in groups or not isinstance(row.get('case_id'),str) or type(row.get('correct')) is not bool:
            raise ValueError('Logs require arm, case_id, and adjudicated boolean correct')
        for metric in ('turns','model_cost','latency_seconds'):
            if metric in row and (type(row[metric]) not in {int,float} or not __import__('math').isfinite(row[metric]) or row[metric]<0):
                raise ValueError('Invalid measurement')
        groups[row['arm']].append(row)
    ids=[{r['case_id'] for r in group} for group in groups.values()]
    paired=set.intersection(*ids)
    if any(len({r['case_id'] for r in group})!=len(group) for group in groups.values()):
        raise ValueError('Duplicate arm/case records')
    report={'paired_cases':len(paired),'unpaired_cases':{arm:sorted({r['case_id'] for r in group}-paired) for arm,group in groups.items()},'arms':{}}
    for arm,group in groups.items():
        selected=[r for r in group if r['case_id'] in paired]
        report['arms'][arm]={'cases':len(selected),'accuracy':sum(r['correct'] for r in selected)/len(selected) if selected else None}
        for metric in ('turns','model_cost','latency_seconds'):
            values=[r[metric] for r in selected if metric in r]
            report['arms'][arm][metric]={'measured_cases':len(values),'mean':sum(values)/len(values) if values else None}
    return report


def run(logs=None):
    kb=KB();fixtures,digest=resource('evaluation-cases.json')
    records=[]
    for case in fixtures['cases']:
        for method in ('legacy_overlap','weighted_evidence','pilot_workflow'):
            start=time.perf_counter()
            if method=='legacy_overlap':ranked=legacy(kb,case['observations']);tied=None
            elif method=='weighted_evidence':
                result=kb.rank(case['observations'],True,100);ranked=[c['disease']['id'] for c in result['candidates']];tied=next((c['rank'] for c in result['candidates'] if c['disease']['id']==case['gold']),None)
            else:
                result=kb.suggest(case['observations'],'pilot');ranked=[c['disease']['id'] for c in result['ranking']['candidates']];tied=next((c['rank'] for c in result['ranking']['candidates'] if c['disease']['id']==case['gold']),None)
            records.append({'case':case['id'],'method':method,'gold':case['gold'],'gold_position':ranked.index(case['gold'])+1 if case['gold'] in ranked else None,'gold_tie_rank':tied,'top_5':ranked[:5],'latency_seconds':round(time.perf_counter()-start,6)})
    report={'scope':fixtures['kind'],'data_version':kb.version,'data_sha256':kb.sha256,'fixture_sha256':digest,'ranking_results':records,'actual_agent_comparison':evaluate_logs(logs) if logs else {'status':'not_run','reason':'No Doctor Agent implementation, SDK, adjudicated evaluation cases, or three-arm execution logs supplied. Ranking fixtures are not agent accuracy or clinical validation.'}}
    target=ROOT/'docs'/'agent-evaluation.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ranking_runs':len(records),'real_agent_comparison':report['actual_agent_comparison'].get('status','evaluated')},ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--agent-logs');run(p.parse_args().agent_logs)
