"""Aggregate local S2 run checks without publishing clinical text or credentials."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=('nova_agent/safety_obligations.py','nova_agent/e2_safety_obligations.py','nova_agent/safety_trace.py')

def main():
    runs=[]
    for p in sorted((ROOT/'results').glob('*_safety_session_R3a_obligations')):
        manifest=json.loads((p/'manifest.json').read_text())
        rows=[json.loads(l) for l in (p/'trace.jsonl').read_text().splitlines()]
        row={'run':p.name,'completed':False,
             'http_error_codes':[r.get('code') for r in rows if r.get('event')=='http_error'],
             'source_matches_current':all(manifest['fingerprint'].get(f)==hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES)}
        if (p/'timeline.json').exists():
            data=json.loads((p/'timeline.json').read_text());audit=data.get('obligations') or {}
            row.update({'record_versions':len(audit.get('versions',[])),
                        'obligations_by_version':[len(v['obligations']) for v in audit.get('versions',[])],
                        'delivered_by_version':[sum(x['state']=='sent_success' for x in v['obligations']) for v in audit.get('versions',[])],
                        'unresolved_current':len(audit.get('unresolved_ids',[])),
                        'coverage_verified':audit.get('coverage_verified',False),
                        'events':[{'event':e['event'],'reason':e.get('reason'),'error':e.get('error')} for e in audit.get('events',[])]})
            if data.get('final'):
                education=data['final']['note']['P']['education']
                marker='실제 전달 기록(API 성공 응답 기준; 이해 여부 미확인):'
                assert marker in education
                row['deterministic_performed_section']=True
        if (p/'analysis.json').exists():
            metrics=json.loads((p/'analysis.json').read_text())
            row.update({k:metrics[k] for k in ('completed','elapsed_seconds','max_server_turn','doctor_successful_request_ids','doctor_attempted_request_ids','truncated_completions')})
        runs.append(row)
    probes=[]
    for path in sorted((ROOT/'results').glob('*_obligation_planning_probe/result.json')):
        item=json.loads(path.read_text())
        probes.append({'run':path.parent.name,'accepted':item['accepted'],'validated':item['validated'],
                       'sent_to_patient':False,
                       'source_matches_current':all(item['fingerprint'].get(f)==hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES)})
    report={'planning_probes':probes,'scope':'development API, not official score; unextracted obligations remain unknown', 'runs':runs,
            'runtime_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}}
    (ROOT/'reports/obligations_live_042.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
