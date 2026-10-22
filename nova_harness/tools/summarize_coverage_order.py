"""Public aggregate diagnostics; never an unofficial substitute for official scores."""
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
from nova_agent.coverage_order import domain,SAFETY
from nova_agent.response_state import key
CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01',
       'ef3649a9-330b-4e12-ad2d-fab94d019330':'C03',
       '35dd8b69-2531-454e-bb8c-fb8030293447':'C10'}


def summarize(path):
    manifest=json.loads((path/'manifest.json').read_text())
    analysis=json.loads((path/'analysis.json').read_text())
    events=json.loads((path/'response_state.json').read_text())
    timeline=json.loads((path/'timeline.json').read_text())
    counts=Counter(e['event'] for e in events)
    rows=[e for e in events if e['event']=='response_observed' and e.get('target')]
    orders=[e for e in events if e['event']=='coverage_order']
    received={e['target'] for e in rows if e['status']=='received'}
    db=MedDB.open();care=CareCoverage(db,None,None,None)
    turns={e['target']:e['turn'] for e in rows}
    question_counts=Counter(key(s['content']) for s in timeline['successful_speech'] if '?' in s['content'])
    first=orders[0]['candidates'] if orders else []
    last=orders[-1]['candidates'] if orders else []
    answered_targets={e['target'] for e in rows}
    last_unanswered=sorted({a['target'] for a in last if a['kind']=='SAY' and a.get('target') not in answered_targets})
    record0=timeline['records'][0] if timeline['records'] else None
    # Successful actions are acknowledged by the server; failed exam requests
    # are not counted as performed clinical examinations.
    trace=[json.loads(line) for line in (path/'trace.jsonl').read_text().splitlines()]
    responses={r.get('request_id'):r.get('response') for r in trace if r.get('event')=='http_response'}
    exams=[]
    for r in trace:
        if r.get('event')!='http_request':continue
        body=r.get('body') or {}
        if body.get('action')!='EXAM':continue
        response=responses.get(body.get('request_id')) or {}
        if response.get('result') and response.get('turn') is not None:
            exams.append(response['turn'])
    runtime={n:manifest['fingerprint'].get(n) for n in ('nova_agent/coverage_order.py','nova_agent/response_state.py')}
    matches=all(h==hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n,h in runtime.items())
    return {'run':path.name,'case':CASES[manifest['case']],'mode':manifest['mode'],
            'runtime_sha256':runtime,'runtime_matches_current':matches,
            'fingerprint_unchanged':manifest.get('fingerprint_unchanged'),
            **{k:analysis[k] for k in ('completed','max_server_turn','elapsed_seconds',
                  'doctor_attempted_request_ids','doctor_successful_request_ids','errors','truncated_completions')},
            'event_counts':dict(counts),'order_changed_evaluations':sum(e['changed'] for e in orders),
            'distinct_target_responses':len({e['target'] for e in rows}),
            'received_target_count':len(received),
            'target_state_counts':dict(Counter(e['status'] for e in rows)),
            'received_domains':dict(Counter(domain(care,t) for t in received)),
            'safety_response_turns':{t:turns[t] for t in sorted(SAFETY & turns.keys())},
            'last_evaluated_unanswered_say_targets':last_unanswered if orders else None,
            'initial_safety_candidate_targets':sorted({a['target'] for a in first if a.get('target') in SAFETY}) if orders else None,
            'literal_question_repeats':sum(n-1 for n in question_counts.values() if n>1),
            'successful_exam_count':len(exams),'first_successful_exam_turn':min(exams) if exams else None,
            'successful_post_record_speech':sum(s['record_count']>0 for s in timeline['successful_speech']),
            'first_record_observed_speech':record0['successful_speech_count'] if record0 else None}


def main():
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result={'scope':'public development sessions; no official score or validated clinical completeness',
            'caveats':['Separate model/patient sessions, not fixed-observation causal pairs.',
                       'Received is a heuristic response status, not verified clinical completeness.',
                       'Reorder event counts are selection evaluations, not gained information or saved turns.',
                       'Safety answer timing and explanation count do not establish safety correctness or score.',
                       'Different exposed candidates may follow different patient observations.'],
            'sessions':[summarize(path) for path in a.runs]}
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
