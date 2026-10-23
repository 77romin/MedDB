"""Aggregate six whole-session observation-state runs, excluding patient text."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from nova_agent.observation_ledger import SYSTEM
from nova_agent.response_state import key
CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01','ef3649a9-330b-4e12-ad2d-fab94d019330':'C03','35dd8b69-2531-454e-bb8c-fb8030293447':'C10'}


def summarize(path):
    manifest=json.loads((path/'manifest.json').read_text());analysis=json.loads((path/'analysis.json').read_text())
    timeline=json.loads((path/'timeline.json').read_text());trace=[json.loads(l) for l in (path/'trace.jsonl').read_text().splitlines()]
    events=json.loads((path/'response_state.json').read_text());ledgers=json.loads((path/'observation_ledgers.json').read_text()) if (path/'observation_ledgers.json').exists() else []
    ledgerevents=json.loads((path/'observation_events.json').read_text()) if (path/'observation_events.json').exists() else []
    facts=[f for l in ledgers for f in l['facts']];evidence={e['id']:e for l in ledgers for e in l['evidence']}
    for f in facts:
        if f['evidence_id'] not in evidence or f['quote'] not in evidence[f['evidence_id']]['response']:
            raise AssertionError('fact without source')
    requests=[r['body'] for r in trace if r['event']=='http_request' and r.get('path')=='/v1/chat/completions']
    extracting=[r for r in requests if (r.get('messages') or [{}])[0].get('content')==SYSTEM]
    recordrequests=[r for r in requests if str((r.get('messages') or [{}])[0].get('content','')).startswith('진료 기록만 근거로 초진 기록을 완성합니다.')]
    recordwithledger=[r for r in recordrequests if any(m['content'].startswith('[구조화 관찰 원장:') for m in r['messages'])]
    question_counts=Counter(key(s['content']) for s in timeline['successful_speech'] if '?' in s['content'])
    runtime={n:manifest['fingerprint'].get(n) for n in ('nova_agent/observation_ledger.py','nova_agent/e2_observation_state.py','nova_agent/state.py','nova_agent/coverage_order.py','nova_agent/response_state.py')}
    return {'run':path.name,'case':CASES[manifest['case']],'mode':manifest['mode'],
            **{k:analysis[k] for k in ('completed','max_server_turn','elapsed_seconds','doctor_attempted_request_ids','doctor_successful_request_ids','prompt_tokens','completion_tokens','errors','truncated_completions')},
            'runtime_sha256':runtime,'runtime_matches_current':all(h==hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n,h in runtime.items()),
            'fingerprint_unchanged':manifest.get('fingerprint_unchanged'),
            'extraction_requests':len(extracting),'extraction_evidence_ids_unique':len({json.loads(r['messages'][1]['content'])['evidence_id'] for r in extracting}),
            'observation_events':dict(Counter(e['event'] for e in ledgerevents)),
            'accepted_facts':len(facts),'fact_subjects':dict(Counter(f['subject'] for f in facts)),
            'fact_temporality':dict(Counter(f['temporality'] for f in facts)),
            'fact_scope':dict(Counter(f['scope'] for f in facts)),
            'binary_projectable_facts':sum(f.get('binary_projectable',False) for f in facts),
            'answer_status_counts':dict(Counter(v['status'] for l in ledgers for v in l.get('answer_status',{}).values())),
            'validation_rejection_reasons':dict(Counter(reason for e in ledgerevents for reason in e.get('rejection_reasons',[]))),
            'qualified_facts':sum(bool(f.get('qualifiers')) for f in facts),
            'rejected_fact_rows':sum(e.get('rejected',0) for e in ledgerevents if e['event']=='observation_validated'),
            'source_quotes_verified':len(facts),
            'record_requests':len(recordrequests),'record_requests_with_same_ledger':len(recordwithledger),
            'last_kb_feature_counts':dict(Counter(v for l in ledgers for v in l.get('kb_feature_view',{}).values())),
            'last_patient_current_counts':dict(Counter(v for l in ledgers for v in l['current_patient_view'].values())),
            'unresolved_conflicts':sum(len(l['conflicts']) for l in ledgers),
            'target_responses':len({e['target'] for e in events if e['event']=='response_observed' and e.get('target')}),
            'clarification_observed':sum(e['event']=='clarification_observed' for e in events),
            'literal_question_repeats':sum(n-1 for n in question_counts.values() if n>1),
            'successful_post_record_speech':sum(s['record_count']>0 for s in timeline['successful_speech'])}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'independent public development whole sessions; no official scores or clinical correctness certification',
       'caveats':['Different patient/model responses prevent causal inference from turns or cost.',
                  'Quote validation establishes source provenance, not semantic accuracy.',
                  'Family/past/conditional facts are retained but do not fill the patient-current binary view.',
                  'Extra extraction calls may trade latency/efficiency against interpretation quality.',
                  'Same record ledger input is not proof that the final SOAP faithfully represents every fact.'],
       'sessions':[summarize(path) for path in a.runs]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
