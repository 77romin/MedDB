"""Replay actual Doctor completions through current observation validation.

Model input equivalence is checked. Validator changes may alter the projection;
that is reported separately from generating a new model response.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from meddb import MedDB
from nova_agent.observation_ledger import ObservationLedger


def replay(path):
    saved=json.loads((path/'results.json').read_text())
    rows=[json.loads(line) for line in (path/'trace.jsonl').read_text().splitlines()]
    responses={r.get('request_id'):r.get('response') for r in rows if r['event']=='http_response'}
    requests={}
    for r in rows:
        if r['event']!='http_request' or r.get('path')!='/v1/chat/completions':continue
        body=r['body'];source=json.loads(body['messages'][1]['content'])
        requests[(source['question'],source['response'],source['target'])]=(body,responses[body['request_id']])
    result=[]
    for case in saved['cases']:
        src=case['synthetic_source'];key=(src['question'],src['response'],src['target'])
        body,response=requests[key]
        class Replay:
            def chat(self,messages,**kwargs):
                if messages!=body['messages'] or kwargs['max_tokens']!=body['max_tokens']:
                    raise AssertionError('model input differs')
                return response
        ledger=ObservationLedger(MedDB.open());ledger.state.initial=src.get('patient_context',{})
        ledger.observe(Replay(),*key,1)
        # observe catches extraction errors by design; explicitly inspect replay
        # matching rather than accidentally accepting an input-drift exception.
        if ledger.failures:raise AssertionError('replay failed')
        actual=ledger.view()[0].get(src['target'] or 'palpitations','?')
        result.append({'id':case['id'],'expected':case['expected'],'original_actual':case['actual'],
                       'replayed_actual':actual,'matches_author_criterion':actual==case['expected']})
    return {'run':path.name,'same_saved_model_inputs':True,'cases':result}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    result={'scope':'saved actual model responses through current validator, not new clinical sessions',
            'runs':[replay(path) for path in a.runs]}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
