"""Publish aggregate link provenance, not patient text or unofficial scores."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from nova_agent.response_state import key


def summarize(path):
    m=json.loads((path/'manifest.json').read_text());a=json.loads((path/'analysis.json').read_text())
    e=json.loads((path/'response_state.json').read_text());t=json.loads((path/'timeline.json').read_text())
    refs={s['reply'].get('turn'):s for s in t['successful_speech']}
    linked=[r for r in e if r['event']=='question_link_observed']
    for row in linked:
        observed=refs.get(row['turn'])
        if not observed:raise AssertionError('link without acknowledged SAY')
        content=observed['content']
        from examples.hybrid_comm import EMPATHY
        if content.startswith(EMPATHY):content=content[len(EMPATHY):]
        if hashlib.sha256(content.encode('utf-8')).hexdigest()!=row['question_sha256']:
            raise AssertionError('link question differs from acknowledged SAY')
    runtime={name:m['fingerprint'].get(name) for name in
             ('nova_agent/question_link.py','nova_agent/e2_question_link.py','nova_agent/coverage_order.py','nova_agent/response_state.py')}
    question_counts=Counter(key(s['content']) for s in t['successful_speech'] if '?' in s['content'])
    return {'run':path.name,'mode':m['mode'],'case_uuid':m['case'],
            **{k:a[k] for k in ('completed','max_server_turn','elapsed_seconds','doctor_attempted_request_ids',
                       'doctor_successful_request_ids','errors','truncated_completions')},
            'runtime_sha256':runtime,
            'runtime_matches_current':all(h==hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n,h in runtime.items()),
            'fingerprint_unchanged':m.get('fingerprint_unchanged'),
            'link_events':dict(Counter(r['event'] for r in e if r['event'].startswith('question_link'))),
            'abstention_reasons':dict(Counter(r['reason'] for r in e if r['event']=='question_link_abstained')),
            'observed_link_targets':dict(Counter(r['target'] for r in linked)),
            'observed_link_count':len(linked),
            'observed_link_has_successful_speech':True if linked else None,
            'target_response_count':len({r['target'] for r in e if r['event']=='response_observed' and r.get('target')}),
            'literal_question_repeats':sum(n-1 for n in question_counts.values() if n>1)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'independent public development sessions; no official score or clinical correctness assertion',
       'caveats':['Generated question scope may differ even with the same topic.',
                  'An abstention is not a successful link; proposed is not observed.',
                  'Zero observed links cannot establish live benefit of the new path.',
                  'Different patient/model responses prevent attributing turn/cost differences solely to code.'],
       'sessions':[summarize(path) for path in a.runs]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
