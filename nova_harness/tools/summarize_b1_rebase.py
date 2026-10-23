"""Text-free aggregate of latest-main B1 comparison runs."""
import argparse
from collections import Counter
import json
from pathlib import Path
CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01','ef3649a9-330b-4e12-ad2d-fab94d019330':'C03','35dd8b69-2531-454e-bb8c-fb8030293447':'C10'}

def summarize(path):
    m=json.loads((path/'manifest.json').read_text());a=json.loads((path/'analysis.json').read_text())
    observations=json.loads((path/'b1_observations.json').read_text())
    t=json.loads((path/'timeline.json').read_text())
    return {'run':path.name,'mode':m['mode'],'case':CASES[m['case']],
            'fingerprint_unchanged':m['fingerprint_unchanged'],
            **{k:a[k] for k in ('completed','max_server_turn','elapsed_seconds','doctor_attempted_request_ids','prompt_tokens','completion_tokens','errors','truncated_completions')},
            'observation_states':dict(Counter(x['status'] for x in observations)),
            'linked_observation_rows':sum(bool(x['links']) for x in observations),
            'record_count':len(t['records']),'successful_speech':len(t['successful_speech']),
            'interpretation_additional_model_calls':0 if m['mode']=='B1O1' else None,
            'source_sha256':m['fingerprint'].get('examples/reader_b1_observed.py')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    out={'scope':'independent same-window public API sessions; no official scores or clinical completeness claim','sessions':[summarize(x) for x in a.runs]}
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
