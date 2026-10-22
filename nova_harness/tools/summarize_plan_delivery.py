"""Private plan logs -> source-free aggregate, not clinical safety scoring."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from summarize_observation_state import summarize,ROOT


def audit_run(path):
    result=summarize(path)
    plan=json.loads((path/'plan_delivery.json').read_text())
    manifest=json.loads((path/'manifest.json').read_text())
    plan_hash=manifest['fingerprint']['nova_agent/plan_delivery.py']
    timeline=json.loads((path/'timeline.json').read_text())
    groups=plan['groups']
    final=(timeline.get('final') or {}).get('note',{}).get('P',{}).get('education','')
    marker='실제 전달 기록(API 성공 기준; 이해 여부 미확인):'
    if marker not in final:raise AssertionError('missing performed block')
    actual=final.split(marker,1)[1]
    claimed=[line for line in actual.splitlines() if line.startswith('[발화 ')]
    eligible=[s for s in timeline['successful_speech'] if s.get('record_count',0)>0 and '?' not in s['content']]
    expected=['[발화 {}] {}'.format(s['index'],s['content']) for s in eligible]
    if claimed!=expected:raise AssertionError('performed speech differs from acknowledged events')
    result['plan_delivery']={
        'groups':len(groups),'states':dict(Counter(g['state'] for g in groups)),
        'render_states':dict(Counter(g.get('render_state','legacy_validated') for g in groups)),
        'source_fields':dict(Counter(g['source_field'] for g in groups)),
        'critical_groups':sum(g['priority']=='critical' for g in groups),
        'critical_delivered':sum(g['priority']=='critical' and g['state']=='sent_success' for g in groups),
        'plan_changed':plan['plan_changed'],'coverage_verified':False,
        'events':plan['events'],'performed_lines_match_acknowledged_speech':True,
        'performed_lines':len(claimed),'source_sha256':plan_hash,
        'source_matches_current':plan_hash==hashlib.sha256((ROOT/'nova_agent/plan_delivery.py').read_bytes()).hexdigest()}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result={'scope':'public development sessions; anchor/delivery checks are not clinical completeness or official scores',
            'sessions':[audit_run(p) for p in a.runs]}
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
