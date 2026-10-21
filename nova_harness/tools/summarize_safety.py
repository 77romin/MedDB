"""Publish only aggregate safety experiment diagnostics; never patient transcripts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01','ef3649a9-330b-4e12-ad2d-fab94d019330':'C03','35dd8b69-2531-454e-bb8c-fb8030293447':'C10'}
RUNTIME=('nova_agent/safety_trace.py','nova_agent/safety_delivery.py','nova_agent/e2_safety_delivery.py')

def main():
    wanted={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in RUNTIME}
    revision=json.loads((ROOT/'reports/safety_format_revision_041.json').read_text()) if (ROOT/'reports/safety_format_revision_041.json').exists() else {}
    output=[]
    for out in sorted((ROOT/'results').glob('20261022_*_safety_session_*')):
        manifest=json.loads((out/'manifest.json').read_text())
        if manifest['mode'] in ('R3a','R3b'):version=manifest['mode']
        else:
            exact=all(manifest['fingerprint'].get(n)==h for n,h in wanted.items())
            is_live=out.name in revision.get('live_validation_runs',[])
            expected=revision.get('live_runtime_hashes_by_run',{}).get(out.name,{})
            if is_live and not all(manifest['fingerprint'].get(n)==h for n,h in expected.items()):
                raise ValueError('live run source registry mismatch')
            version='S1_current_exact_runtime' if exact else ('S1_live_validation_recorded_source' if is_live else 'S1_intermediate') 
        analysis=json.loads((out/'analysis.json').read_text()) if (out/'analysis.json').exists() else {}
        item={'run':out.name,'case':CASES[manifest['case']],'version':version,'e2_source_matches_current':manifest['fingerprint'].get('nova_agent/e2_safety_delivery.py')==wanted['nova_agent/e2_safety_delivery.py'],'timeline_source_matches_current':manifest['fingerprint'].get('nova_agent/safety_trace.py')==wanted['nova_agent/safety_trace.py'],
              **{k:analysis.get(k) for k in ('completed','max_server_turn','elapsed_seconds','doctor_attempted_request_ids','doctor_successful_request_ids','errors','truncated_completions')}}
        if (out/'timeline.json').exists():
            t=json.loads((out/'timeline.json').read_text());actual=[s['content'] for s in t['successful_speech'] if s['record_count']>0 and '?' not in s['content']]
            note=(t.get('final') or {}).get('note',{});education=note.get('P',{}).get('education','')
            section=education.split('실제 전달 확인(성공 SAY):',1)[-1] if '실제 전달 확인(성공 SAY):' in education else None
            item.update(record_count=len(t['records']),successful_explanation_count=len(actual),
                        explicit_actual_speech_section=section is not None,
                        all_actual_explanations_listed=(all(s in section for s in actual) if section is not None else None))
            if t['records'] and note:
                before=t['records'][-1]['note']
                item['final_reconciliation_changes_only_education']=all(note.get(k)==v for k,v in before.items() if k!='P') and all(note['P'].get(k)==v for k,v in before.get('P',{}).items() if k!='education')
        if (out/'review.json').exists():
            review=json.loads((out/'review.json').read_text())['review']
            item['model_review']={'delivery':dict(Counter(c['delivery'] for c in review['checks'])),
                                  'final_consistency':dict(Counter(c['final_consistency'] for c in review['checks'])),
                                  'unspoken_completed_claims':len(review['unspoken_completed_claims'])}
        if (out/'safety_delivery.json').exists():
            events=json.loads((out/'safety_delivery.json').read_text())['events']
            item['delivery_event_counts']=dict(Counter(e['event'] for e in events))
            item['unresolved_fields']=[e.get('unresolved_fields',[]) for e in events if e['event']=='closing_proposed']
        output.append(item)
    final=[x for x in output if x['version'] in ('S1_current_exact_runtime','S1_live_validation_recorded_source')]
    payload={'scope':'public development API diagnostics, not official scores or clinical correctness',
             'caveats':['Each live session has different patient/doctor interaction; not a paired causal score comparison.',
                        'Model-review checklist items differ per session; do not rank versions by raw category counts.',
                        'Echoed actual speech proves provenance, not full safety coverage or clinical correctness.',
                        'Intermediate versions are included to expose failures, not pooled with final S1.',
                        'Registry: three full validations plus targeted C10 budget regression. A final post-DIAGNOSE-note recommendation-verb cleanup is tested by source reconstruction and note replay; not a new API submission.'],
             'final_runtime_hashes':wanted,'validated_s1_sessions_completed':sum(bool(x.get('completed')) for x in final),
             'sessions':output}
    (ROOT/'reports/safety_metrics_041.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sessions':len(output),'validated_s1_sessions_completed':payload['validated_s1_sessions_completed']}))

if __name__=='__main__':main()
