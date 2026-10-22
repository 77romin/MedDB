"""Deterministic source/render/turn audit of a frozen S2 validation batch."""
from collections import Counter
from copy import deepcopy
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from experiment import fingerprint
from nova_agent.safety_obligations import ObligationLedger
from examples.hybrid_agent import parse_json

def main():
    batch=Path(sys.argv[1]);manifest=json.loads((batch/'manifest.json').read_text());summary=json.loads((batch/'summary.json').read_text())
    reports=[]
    for row in summary['runs']:
        out=Path(row['directory']);t=json.loads((out/'timeline.json').read_text());metrics=json.loads((out/'analysis.json').read_text());o=t['obligations']
        ledger=ObligationLedger();ledger.versions=deepcopy(o['versions']);ledger.events=deepcopy(o['events'])
        expected=ledger.render({'P':deepcopy(o['versions'][-1]['plan'])},t['successful_speech'])
        final=t['final']['note']['P']
        exact_render=all(final.get(k)==v for k,v in expected['P'].items())
        all_speech=Counter(s['content'] for s in t['successful_speech'])
        answered_repeats=0
        for previous,current in zip(t['successful_speech'],t['successful_speech'][1:]):
            if ('?' in current['content'] and current['content']==previous['content']
                and current.get('request_id')!=previous.get('request_id')
                and current.get('reply',{}).get('content')
                and current['reply'].get('content')==previous.get('reply',{}).get('content')):
                answered_repeats+=1
        seen=Counter(s['content'] for s in t['successful_speech'] if s['record_count']>0)
        errors=Counter();valid_rows=0;raw_rows=0
        trace=[json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
        for i,r in enumerate(trace):
            body=r.get('body',{});messages=body.get('messages',[]) if isinstance(body,dict) else []
            if not messages or not messages[0].get('content','').startswith('기존 계획 자료에서 환자에게'):
                continue
            response=next((x for x in trace[i+1:] if x['event']=='http_response'),None)
            try:
                payload=parse_json(response['response']['choices'][0]['message']['content'] or '')
                note={'P':json.loads(messages[-1]['content'])['source_plan']}
                for item in payload['obligations']:
                    raw_rows+=1;candidate=ObligationLedger();candidate.update(note)
                    try:candidate.register({'obligations':[item]});valid_rows+=1
                    except ValueError as exc:errors[str(exc)]+=1
            except Exception as exc:errors['parse_or_shape_'+type(exc).__name__]+=1
        delivery_events=json.loads((out/'safety_delivery.json').read_text())['events']
        unresolved=[e.get('unresolved_fields',[]) for e in delivery_events if e['event']=='closing_proposed']
        report={'s1_unresolved_closing_fields':unresolved[-1] if unresolved else None,
                's1_repair_failures':sum(e['event']=='closing_repair_failed' for e in delivery_events),
                's1_rejected_addendum_groups':sum(e.get('validation',{}).get('rejected_groups',0) for e in delivery_events),
                'case_label':row['case_label'],'run':out.name,
                'runtime_matches_frozen':json.loads((out/'manifest.json').read_text())['fingerprint']==manifest['fingerprint'],
                **{k:metrics[k] for k in ('completed','elapsed_seconds','max_server_turn','doctor_attempted_request_ids','doctor_successful_request_ids','errors','truncated_completions')},
                'deterministic_final_plan_and_performed_render_matches':exact_render,
                'raw_generated_obligations':raw_rows,'individually_valid_rows':valid_rows,'rejection_reasons':dict(errors),
                'registered_obligations_by_version':[len(v['obligations']) for v in o['versions']],
                'sent_obligations_by_version':[sum(r['state']=='sent_success' for r in v['obligations']) for v in o['versions']],
                'consecutive_same_question_same_nonempty_reply_distinct_request':answered_repeats,
                'exact_duplicate_all_messages':sum(n-1 for n in all_speech.values() if n>1),
                'exact_duplicate_post_record_messages':sum(n-1 for n in seen.values() if n>1),
                'coverage_verified':False}
        reports.append(report)
    result={'scope':'frozen final S2 development API audit, not official scoring/clinical completeness',
            'runtime_unchanged_during_batch':summary['runtime_unchanged_during_batch'],
            'current_runtime_matches_frozen':fingerprint()==manifest['fingerprint'],'runs':reports}
    if (batch/'review_summary.json').exists():result['model_review']=json.loads((batch/'review_summary.json').read_text())
    (ROOT/'reports/validation_043.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
