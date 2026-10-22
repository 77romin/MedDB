"""Aggregate only: paired-in-time public sessions are not paired observations."""
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nova_agent.response_state import key
CASES={'4fa07144-04e5-4116-a18e-88d8a90cc21a':'C01',
       'ef3649a9-330b-4e12-ad2d-fab94d019330':'C03',
       '35dd8b69-2531-454e-bb8c-fb8030293447':'C10'}
RUNS=('20261023_001814_238498_safety_session_R3a_response_state',
      '20261023_001817_422022_safety_session_R3a',
      '20261023_002314_586520_safety_session_R3a_response_state',
      '20261023_002318_192872_safety_session_R3a',
      '20261023_002455_428558_safety_session_R3a_response_state',
      '20261023_002456_230620_safety_session_R3a')

def main():
    wanted=hashlib.sha256((ROOT/'nova_agent/response_state.py').read_bytes()).hexdigest()
    sessions=[];sequences={}
    for name in RUNS:
        path=ROOT/'results'/name
        if not (path/'analysis.json').exists():raise ValueError('Session not complete: '+name)
        m=json.loads((path/'manifest.json').read_text());a=json.loads((path/'analysis.json').read_text())
        t=json.loads((path/'timeline.json').read_text())
        es=json.loads((path/'response_state.json').read_text()) if (path/'response_state.json').exists() else []
        row={'run':name,'case':CASES[m['case']],'mode':m['mode'],
             'runtime_sha256':m['fingerprint']['nova_agent/response_state.py'],
             'runtime_matches_current':m['fingerprint']['nova_agent/response_state.py']==wanted,
             'end_fingerprint_unchanged':m.get('fingerprint_unchanged'),
             **{k:a[k] for k in ('completed','max_server_turn','elapsed_seconds',
                    'doctor_successful_request_ids','doctor_attempted_request_ids','errors','truncated_completions')},
             'response_events':dict(Counter(e['event'] for e in es)),
             'target_response_states':dict(Counter(e['status'] for e in es if e['event']=='response_observed' and e.get('target'))),
             'distinct_conflict_targets':sorted({e['target'] for e in es if e['event']=='observed_conflict'}),
             'distinct_filtered_targets':sorted({e['target'] for e in es if e['event']=='answered_filtered' and e.get('target')})}
        question_counts=Counter(key(s['content']) for s in t['successful_speech'] if '?' in s['content'])
        row['literal_question_repeats']=sum(n-1 for n in question_counts.values() if n>1)
        sessions.append(row)
        sequences[(row['case'],row['mode'])]=[s['content'] for s in t['successful_speech'] if s['record_count']==0]
    comparisons=[]
    for case in ('C01','C03','C10'):
        before=sequences[(case,'R3a')];after=sequences[(case,'R3a_response_state')]
        comparisons.append({'case':case,'same_pre_record_speech_sequence':before==after,
                            'baseline_pre_record_speech_count':len(before),'candidate_pre_record_speech_count':len(after)})
    result={'scope':'public development sessions; no official score or validated clinical accuracy',
            'caveats':['Independent patient/model responses, not identical observation pairs or causal effect estimates.',
                       'C03 live source predates Korean quantity fix; complete strict replay with final source is reported separately.',
                       'Received means a non-explicitly-ambiguous response, not verified completeness or a medical fact.',
                       'No inference of safety score from error-free completion.',
                       'Filter/conflict counts count repeated candidate evaluations, not saved turns or independent conflicts.'],
            'current_runtime_sha256':wanted,'sessions':sessions,'comparisons':comparisons}
    (ROOT/'reports/response_state_validation_047.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
