"""Freeze current runtime and run three public API sessions in isolated processes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from experiment import fingerprint
SOURCES={'C01':'20261022_081024_824030_safety_session_R3a_safety',
         'C03':'20261022_081026_065409_safety_session_R3a_safety',
         'C10':'20261022_082006_598639_safety_session_R3a_safety'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['R3a_obligations','R3a_obligations_fixed'],default='R3a_obligations');args=parser.parse_args()
    tag='_s3_full_validation' if args.mode=='R3a_obligations_fixed' else '_s2_full_validation'
    out=ROOT/'results'/(datetime.now().strftime('%Y%m%d_%H%M%S')+tag)
    out.mkdir(mode=0o700)
    frozen=fingerprint()
    cases={label:json.loads((ROOT/'results'/source/'manifest.json').read_text())['case'] for label,source in SOURCES.items()}
    manifest={'scope':'three public development sessions; no official scoring/submission',
              'mode':args.mode,'cases':cases,'fingerprint':frozen}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Validation batch:',out,flush=True)
    def run(item):
        label,case=item
        with (out/(label+'.stdout')).open('w') as stream:
            result=subprocess.run([sys.executable,str(ROOT/'tools/safety_session.py'),'--case',case,'--mode',args.mode],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        text=(out/(label+'.stdout')).read_text()
        directory=next((line.split('Experiment directory: ',1)[1] for line in text.splitlines() if line.startswith('Experiment directory: ')),None)
        summary={'case_label':label,'exit_code':result.returncode,'directory':directory}
        print(json.dumps(summary),flush=True)
        return summary
    with ThreadPoolExecutor(max_workers=3) as pool:
        runs=list(pool.map(run,cases.items()))
    stable=fingerprint()==frozen
    summary={'scope':manifest['scope'],'runtime_unchanged_during_batch':stable,'runs':runs}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert stable,'runtime changed during validation'
    if any(r['exit_code'] for r in runs):raise SystemExit(1)

if __name__=='__main__':main()
