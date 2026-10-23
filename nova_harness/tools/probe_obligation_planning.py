"""One Doctor-only planning probe from saved actual plan; sends no patient speech."""
import json,os,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from experiment import load_local_env,fingerprint
from nova_agent.protocol import LoggedClient
from nova_agent.telemetry import Trace
from nova_agent.e2_safety_obligations import SYSTEM
from nova_agent.safety_obligations import ObligationLedger

def main():
    source=Path(sys.argv[1]);data=json.loads(source.read_text())
    note=data['records'][0]['note']
    load_local_env();key=os.environ['NOVA_DEV_KEY']
    out=ROOT/'results'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_obligation_planning_probe');out.mkdir(mode=0o700)
    trace=Trace(out/'trace.jsonl',secrets=[key])
    client=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    response=client.chat([{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'source_plan':note['P']},ensure_ascii=False)}],model='openai/gpt-6-luna',max_tokens=2048,reasoning_effort='low')
    ledger=ObligationLedger();ledger.update(note)
    result={'scope':'live Doctor-only planning from saved real plan; no SAY, no official score','fingerprint':fingerprint()}
    try:
        rows=ledger.register(json.loads(response['choices'][0]['message']['content']))
        result.update({'accepted':len(rows),'validated':True})
    except (ValueError,KeyError,TypeError) as exc:result.update({'accepted':0,'validated':False,'error':str(exc)})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='fingerprint'}))
    print('Private output:',out)

if __name__=='__main__':main()
