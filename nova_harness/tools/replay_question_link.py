"""Audit finite question links on saved acknowledged speech, no API calls.

Only response events with no original target are considered new link candidates.
No counterfactual clinical effect is inferred. Does not emit patient text.
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
from nova_agent.question_link import QuestionIndex
from examples.consult_skeleton import demographics


def audit(path):
    timeline=json.loads((path/'timeline.json').read_text())
    events=json.loads((path/'response_state.json').read_text())
    # Target-less successful SAYs only: proposals/failed actions never qualify.
    turns={e['turn'] for e in events if e['event']=='response_observed' and e.get('target') is None}
    first=timeline['records'][0]['observation']
    age,sex=demographics(first['opening']);index=QuestionIndex(MedDB.open(),{},age,sex)
    counts=Counter();links=[]
    for s in timeline['successful_speech']:
        if s['reply'].get('turn') not in turns:continue
        target,reason=index.resolve(s['content']);counts[reason]+=1
        if target:links.append({'target':target,'turn':s['reply']['turn'],'speech_index':s['index'],
                               'question_sha256':hashlib.sha256(s['content'].encode()).hexdigest()})
    return {'run':path.name,'timeline_sha256':hashlib.sha256((path/'timeline.json').read_bytes()).hexdigest(),
            'targetless_successful_speech':sum(counts.values()),'resolution_counts':dict(counts),
            'proposed_links_not_counterfactual_results':links}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'saved actual target-less successful speech, not new clinical sessions or score',
       'runtime_sha256':hashlib.sha256((ROOT/'nova_agent/question_link.py').read_bytes()).hexdigest(),
       'sessions':[audit(path) for path in a.runs]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
