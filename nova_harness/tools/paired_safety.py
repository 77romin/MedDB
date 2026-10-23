"""Live Doctor R3a/R3b comparison on identical saved observations; no patient actions.

Prefix patient/exam replies are saved observations. Record, retrieval selection,
query generation, and closing generation are NEW development API calls. Generated
closing text is an unsent proposal; never label it actual patient communication.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from experiment import load_local_env
from replay_e2_session import ReplayClient,_load,consult,prepare
from nova_agent.protocol import LoggedClient
from nova_agent.telemetry import Trace
from nova_agent.safety_trace import digest
from nova_agent.rag_retrieval import VectorStore
from nova_agent import e2_rag_selection,e2_rag_query,e2_rag

class Captured(BaseException):pass

def capture(path):
    from examples import hybrid_agent as H
    session,calls=_load(path);client=ReplayClient(session,calls);captured={}
    old=H.write_record
    def stop(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        captured['args']=(db,kb,opening,vitals,list(transcript),contextual_plan)
        raise Captured()
    H.write_record=stop
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    except Captured:pass
    finally:H.write_record=old
    if not captured:raise ValueError('no record boundary found')
    return client.session(),captured['args']

class ObservationClient:
    def __init__(self,raw,session):self.raw=raw;self.initial=deepcopy(session)
    def session(self):return deepcopy(self.initial)
    def chat(self,messages,**kwargs):
        return self.raw.chat(messages,model='openai/gpt-6-luna',**kwargs)


def main():
    p=argparse.ArgumentParser();p.add_argument('trace');p.add_argument('--label',default='paired');args=p.parse_args()
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Key missing; configure locally.')
    if os.environ.get('NOVA_API_BASE','https://nova.snubhai.org').rstrip('/')!='https://nova.snubhai.org':raise SystemExit('Official origin required')
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S_%f')
    out=ROOT/'results'/f'{stamp}_paired_safety_{args.label}';out.mkdir(mode=0o700)
    trace=Trace(out/'trace.jsonl',secrets=[key]);raw=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    source=Path(args.trace);source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    deadline=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
    results=[]
    # Each arm reconstructs the SAME patient/exam input; no new patient interaction.
    for mode,module in [('R3a',e2_rag_selection),('R3b',e2_rag_query)]:
        session,record_args=capture(source)
        session['deadline']=deadline
        db,kb,opening,vitals,transcript,contextual=record_args
        observed_hash=digest({'opening':opening,'vitals':vitals,'transcript':transcript})
        client=ObservationClient(raw,session)
        store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
        previous=module.install(store)
        try:
            from examples import hybrid_agent as H, hybrid_comm as C
            note,diagnosis=H.write_record(client,*record_args)
            proposed=C._closing_sentences(client,db,note,diagnosis,'',comprehensive=True)
            item={'mode':mode,'observation_hash':observed_hash,'note':note,'diagnosis':diagnosis,
                  'proposed_not_sent':proposed,'selector':deepcopy(e2_rag_selection.LAST_RUN),
                  'query':deepcopy(e2_rag_query.LAST_RUN) if mode=='R3b' else None,
                  'retrieval':deepcopy(e2_rag.LAST_RUN)}
            results.append(item);trace.emit('paired_arm',**item)
        finally:module.restore(previous);store.close()
    assert results[0]['observation_hash']==results[1]['observation_hash']
    (out/'comparison.json').write_text(json.dumps({'scope':'live Doctor, fixed saved observations; speech proposals NOT delivered; no official score',
        'source_trace_sha256':source_hash,'deadline_policy':'same fresh 30-minute model-only comparison window','arms':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'equal_observation_hash':True,'modes':[r['mode'] for r in results]}),flush=True)

if __name__=='__main__':main()
