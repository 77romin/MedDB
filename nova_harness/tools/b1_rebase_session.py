"""Run merged-main B1/B2; old vendor/meddb and Q1 are never imported."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
TEAM=ROOT.parent if (ROOT.parent/'examples/agent_b1.py').exists() else ROOT/'vendor/meddb-publish'
sys.path[:0]=[str(TEAM),str(ROOT),str(ROOT/'tools')]
from experiment import load_local_env
from nova_agent.protocol import LoggedClient,Gateway
from nova_agent.telemetry import Trace
from nova_agent.analysis import write_report
from nova_agent.safety_trace import SafetyTimeline,TimelineClient,install,restore
from meddb import MedDB
from examples import agent_b1,agent_b1_observed,reader_b1_observed

def fingerprint():
    paths=[*sorted((TEAM/'examples').glob('*.py')),*sorted((TEAM/'meddb').rglob('*.py')),
           *sorted((TEAM/'meddb/data').glob('*'))]
    return {p.relative_to(TEAM).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--mode',choices=['B1','B1O1'],required=True);a=p.parse_args()
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Missing development key')
    spec=importlib.util.spec_from_file_location('run',ROOT/'vendor/starter/run.py')
    starter=importlib.util.module_from_spec(spec);sys.modules['run']=starter;spec.loader.exec_module(starter)
    out=ROOT/'results'/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_main_'+a.mode);out.mkdir(mode=0o700)
    m={'mode':a.mode,'case':a.case,'scope':'public development; no official score','fingerprint':fingerprint()}
    (out/'manifest.json').write_text(json.dumps(m,indent=2))
    trace=Trace(out/'trace.jsonl',secrets=[key]);raw=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    trace.emit('experiment_start',manifest=m);Gateway(raw,trace=trace).invoke('create_sample',a.case)
    timeline=SafetyTimeline(trace);old=install(timeline);observations=[];original=reader_b1_observed.observe
    def observe(*args):
        original(*args);observations.append(deepcopy(args[0].b1_observations[-1]))
    reader_b1_observed.observe=observe
    print('Experiment directory:',out,flush=True)
    try:
        result=(agent_b1 if a.mode=='B1' else agent_b1_observed).consult(TimelineClient(raw,timeline),MedDB.open())
        trace.emit('experiment_complete',outcome=result)
    finally:
        reader_b1_observed.observe=original;restore(old)
        (out/'timeline.json').write_text(json.dumps(timeline.snapshot(),ensure_ascii=False))
        (out/'b1_observations.json').write_text(json.dumps(observations,ensure_ascii=False))
    m['fingerprint_unchanged']=m['fingerprint']==fingerprint();(out/'manifest.json').write_text(json.dumps(m,indent=2))
    print(json.dumps(write_report(out/'trace.jsonl'),ensure_ascii=False))
if __name__=='__main__':main()
