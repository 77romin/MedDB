"""Execute a bounded, resumable plan against frozen source directories, without copying keys."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.experiment import load_local_env


def run_job(job,environment):
    source=(ROOT/job['source']).resolve()
    if not source.is_relative_to(ROOT/'results') or not (source/'tools/experiment.py').is_file():
        raise ValueError('suite sources must be frozen below results/')
    flags=job.get('flags',[])
    if any(flag not in {'--full-context','--guidelines'} for flag in flags):raise ValueError('invalid suite flag')
    for p in (source/'results').glob('*/manifest.json'):
        m=json.loads(p.read_text())
        if m.get('label')==job['label']:
            a=p.parent/'analysis.json'
            if a.exists() and json.loads(a.read_text()).get('completed'):
                return {'label':job['label'],'directory':str(p.parent),'returncode':0,'reused':True}
            raise ValueError('existing unfinished run; inspect before retrying '+job['label'])
    args=[sys.executable,str(source/'tools/experiment.py'),'run','--agent','harness','--max-turns','45',
          '--case',job['case_id'],'--label',job['label'],*flags]
    print('Starting '+job['label'],flush=True)
    log=ROOT/'results'/('suite_'+job['label']+'.log')
    with log.open('w') as stream:
        result=subprocess.run(args,cwd=source,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    match=next((p.parent for p in (source/'results').glob('*/manifest.json')
                if json.loads(p.read_text()).get('label')==job['label']),None)
    print('Finished '+job['label']+' status '+str(result.returncode),flush=True)
    return {'label':job['label'],'directory':str(match) if match else None,'returncode':result.returncode,'reused':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan');parser.add_argument('--workers',type=int,choices=[1,2,3],default=2)
    args=parser.parse_args();path=Path(args.plan);jobs=json.loads(path.read_text())
    if not isinstance(jobs,list) or len(jobs)>24:raise ValueError('bounded plan requires at most 24 jobs')
    load_local_env();environment=os.environ.copy();environment.pop('PYTHONPATH',None)
    if not environment.get('NOVA_DEV_KEY'):raise ValueError('NOVA_DEV_KEY missing')
    ledger=path.with_suffix('.ledger.json');records=json.loads(ledger.read_text()) if ledger.exists() else []
    for start in range(0,len(jobs),args.workers):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(run_job,job,environment) for job in jobs[start:start+args.workers]]
            for future in as_completed(futures):
                value=future.result();records.append(value);ledger.write_text(json.dumps(records,ensure_ascii=False,indent=2))
        if any(r['returncode'] for r in records):raise SystemExit('Suite stopped after failed run; inspect logs.')
    print('Suite complete: '+str(len(jobs))+' planned jobs',flush=True)

if __name__=='__main__':main()
