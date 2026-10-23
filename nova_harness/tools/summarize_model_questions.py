"""Text-free comparison of model question selection and fixed observation control."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from summarize_observation_state import summarize,ROOT


def summarize_run(path):
    result=summarize(path)
    analysis=json.loads((path/'analysis.json').read_text())
    result['prompt_tokens']=analysis.get('prompt_tokens')
    result['completion_tokens']=analysis.get('completion_tokens')
    events=json.loads((path/'response_state.json').read_text())
    manifest=json.loads((path/'manifest.json').read_text())
    selections=[e for e in events if e['event']=='question_policy']
    first=None;nonfirst=0
    for e in events:
        if e['event']=='coverage_order':
            first=(e.get('ordered_targets') or [None])[0]
        elif e['event']=='question_policy' and e.get('selection','').startswith('model_'):
            nonfirst+=first is not None and e.get('target')!=first
    result['policy']={'selection_evaluations':dict(Counter(e['selection'] for e in selections)),
                      'different_from_first_required_evaluations':nonfirst,
                      'rejected_proposals':dict(Counter(e['reason'] for e in events if e['event']=='question_policy_rejected')),
                      'clinical_information_gain_measured':False}
    h=manifest['fingerprint']['nova_agent/model_question_policy.py']
    result['policy']['source_sha256']=h
    result['policy']['source_matches_current']=h==hashlib.sha256((ROOT/'nova_agent/model_question_policy.py').read_bytes()).hexdigest()
    result['policy']['received_slots']=sum(e['event']=='response_observed' and e.get('status')=='received' for e in events)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    out={'scope':'same-window independent public development sessions; no official scores',
         'caveats':['Different model/patient responses; not fixed-observation causal pairs.',
                    'Selection events are evaluations, not necessarily executed or clinically valuable actions.',
                    'Fact counts and literal repetitions do not measure clinical coverage or semantic repetitions.',
                    'Source provenance and replay fidelity do not establish clinical correctness or safety completeness.'],
         'sessions':[summarize_run(path) for path in a.runs]}
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))
