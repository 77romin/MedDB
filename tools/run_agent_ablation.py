"""Plan or explicitly execute the same agent command under three knowledge modes.
Default is plan-only; no model calls, subprocess agent execution, or credential inspection.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from compare_knowledge_offline import freeze_revision,BASE_REVISION,IMPROVED_REVISION,ROOT


def validate_output(row,case,arm):
    if not isinstance(row,dict) or row.get('case_id')!=case or row.get('arm')!=arm:raise ValueError('Agent output must identify exact arm and case')
    if not isinstance(row.get('diagnosis'),str) or not row['diagnosis'].strip():raise ValueError('Missing diagnosis')
    for metric in ('turns','model_cost','latency_seconds'):
        if metric in row and (type(row[metric]) not in {int,float} or not __import__('math').isfinite(row[metric]) or row[metric]<0):raise ValueError('Invalid metric')
    return row


def run(command,cases,execute=False,timeout=1800):
    if not isinstance(command,list) or not command or any(not isinstance(x,str) or not x for x in command):raise ValueError('Command must be a nonempty JSON string array')
    if not cases or len(set(cases))!=len(cases) or any(not isinstance(c,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}',c) for c in cases):raise ValueError('Provide unique safe case IDs')
    if type(timeout) is not int or not 1<=timeout<=3600:raise ValueError('Timeout must be 1-3600 seconds')
    root=ROOT/'.run/agent-ablation';root.mkdir(parents=True,exist_ok=True)
    manifests={arm:freeze_revision(ref,root/arm) for arm,ref in [('previous_kb',BASE_REVISION),('improved_kb',IMPROVED_REVISION)]}
    jobs=[{'case_id':case,'arm':arm,'command':command,'environment':{'NOVA_KB_MODE':arm,'NOVA_KB_SNAPSHOT_DIR':str(root/arm) if arm!='no_kb' else '', 'NOVA_COMPARISON_CASE_ID':case},'output':str(root/f'{case}-{arm}.json')} for case in cases for arm in ('no_kb','previous_kb','improved_kb')]
    plan={'execution_requested':execute,'agent_contract':'Same agent command and model settings across arms; adapter must honor NOVA_KB_MODE, never read sample scripts/answers or identify a fixed answer by case ID. Return one JSON result on stdout. Independent correct adjudication is added later.','knowledge_revisions':{a:m['revision'] for a,m in manifests.items()},'jobs':jobs}
    (root/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    if not execute:
        print(json.dumps({'status':'plan_only','jobs':len(jobs),'agent_executed':False,'plan':str(root/'plan.json')}));return
    results=[]
    for job in jobs:
        environment=dict(os.environ,**job['environment'])
        completed=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,encoding='utf-8',timeout=timeout,check=True)
        row=validate_output(json.loads(completed.stdout),job['case_id'],job['arm'])
        row['knowledge_revision']=plan['knowledge_revisions'].get(job['arm'])
        Path(job['output']).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');results.append(row)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'executed','runs':len(results)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--agent-command-json',required=True);p.add_argument('--cases',nargs='+',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--timeout',type=int,default=1800);a=p.parse_args();run(json.loads(a.agent_command_json),a.cases,a.execute,a.timeout)
