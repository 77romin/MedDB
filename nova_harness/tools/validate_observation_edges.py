"""Live fixed synthetic observations, no patient session or official submission.

Expected propositions are author-defined and never sent to the Doctor. Comparison
is with frozen original helper outcomes on the same synthetic inputs, not scores.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from experiment import load_local_env,fingerprint
from meddb import MedDB
from nova_agent.protocol import LoggedClient
from nova_agent.telemetry import Trace
from nova_agent.observation_ledger import ObservationLedger

CASES=[
 ('E01','복통이 있나요?','설사는 없어요.','abdominal_pain','?'),
 ('E02','지금 설사가 있나요?','예전에는 있었지만 지금은 없어요.','diarrhea','-'),
 ('E03','설사가 있나요?','거의 없어요.','diarrhea','?'),
 ('E04','설사가 있나요?','아니요, 없다는 뜻이 아니라 설사가 있어요.','diarrhea','+'),
 ('E05','', '어머니는 두근거림이 있어요.',None,'?'),
 ('V01','복통이 있나요?','설사는 없고 배가 아픈지는 모르겠어요.','abdominal_pain','?'),
 ('V02','지금 설사가 있나요?','지금은 설사가 없어요. 작년에만 있었어요.','diarrhea','-'),
 ('V03','설사가 있나요?','설사가 있는지 없는지 모르겠어요.','diarrhea','?'),
 ('V04','설사가 있나요?','아까 없다고 잘못 말했어요. 지금은 설사를 해요.','diarrhea','+'),
 ('V05','가슴이 두근거리나요?','저는 두근거림이 없고 어머니만 있어요.','palpitations','-'),
]


def main():
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Local development key missing')
    if os.environ.get('NOVA_API_BASE','https://nova.snubhai.org').rstrip('/')!='https://nova.snubhai.org':raise SystemExit('Official origin required')
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S_%f')
    out=ROOT/'results'/f'{stamp}_observation_edges';out.mkdir(mode=0o700)
    start=fingerprint();trace=Trace(out/'trace.jsonl',secrets=[key])
    client=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    print('Experiment directory:',out,flush=True)
    def run(case):
        id,question,answer,target,expected=case
        ledger=ObservationLedger(MedDB.open())
        ledger.observe(client,question,answer,target,1)
        fid=target or 'palpitations';view,conflicts=ledger.view();actual=view.get(fid,'?')
        return {'id':id,'expected':expected,'actual':actual,'matches_author_criterion':actual==expected,
                'snapshot':ledger.snapshot(),'events':ledger.events,'synthetic_source':{'question':question,'response':answer,'target':target}}
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,CASES))
    payload={'scope':'live Doctor on fixed author-defined synthetic observations; no patient/official score',
             'fingerprint':start,'end_fingerprint':fingerprint(),'fingerprint_unchanged':start==fingerprint(),
             'cases':results}
    (out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    aggregate={'scope':payload['scope'],'run':out.name,'fingerprint_unchanged':payload['fingerprint_unchanged'],
               'cases':[{'id':r['id'],'expected':r['expected'],'actual':r['actual'],
                         'matches_author_criterion':r['matches_author_criterion'],'accepted_facts':len(r['snapshot']['facts']),
                         'interpretation_failures':len(r['snapshot']['failures'])} for r in results]}
    (ROOT/'reports/observation_edges_live_051.json').write_text(json.dumps(aggregate,indent=2)+'\n')
    print(json.dumps(aggregate),flush=True)

if __name__=='__main__':main()
