"""Aggregate classification of saved acknowledged replies; no API calls.

Only unambiguously matched canonical questions are included. This measures
classification, not counterfactual next actions, SOAP accuracy, or scores.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from meddb import MedDB
from meddb.coverage import CareCoverage
from nova_agent.response_state import key,classify


def summarize(path):
    db=MedDB.open();mapping={}
    for target,row in {**db.slots,**db.findings}.items():
        if row.get('ask'):mapping.setdefault(key(row['ask']),set()).add(target)
    for target,(question,_) in CareCoverage(db,None,None,None).extra.items():
        mapping.setdefault(key(question),set()).add(target)
    data=json.loads(path.read_text());states=Counter();matched=0
    for speech in data['successful_speech']:
        targets=mapping.get(key(speech['content']),set())
        if len(targets)!=1:continue
        matched+=1
        states[classify(next(iter(targets)),speech['reply']['content'])]+=1
    return {'run':path.parent.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'successful_speech':len(data['successful_speech']),
            'canonical_question_matches':matched,'response_states':dict(states)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('timelines',nargs='+',type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    result={'scope':'saved successful replies, canonical-question subset; not scores or counterfactual sessions',
            'runtime_sha256':hashlib.sha256((ROOT/'nova_agent/response_state.py').read_bytes()).hexdigest(),
            'runs':[summarize(p) for p in args.timelines]}
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
