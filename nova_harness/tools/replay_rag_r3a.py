"""Integration replay with explicitly synthetic selector decisions; never a score."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from replay_rag_r1 import RagReplay, _load, consult, prepare
from nova_agent import e2_rag_selection
from nova_agent.rag_selector import SYSTEM
from nova_agent.rag_retrieval import VectorStore


class FixtureReplay(RagReplay):
    def __init__(self,session,calls,accept):
        super().__init__(session,calls);self.accept=accept;self.selector_calls=0

    def chat(self,messages,max_tokens):
        if messages[0]['content']==SYSTEM:
            self.selector_calls+=1
            inputs=json.loads(messages[1]['content'])
            initial=inputs['patient_observations'][0]
            decisions=[{'chunk_id':d['chunk_id'],'status':'usable' if self.accept else 'uncertain',
                        'reason':'Synthetic integration fixture only; not a clinical decision',
                        'patient_evidence':[{'id':initial['id'],'quote':initial['content'][:80]}],
                        'source_quote':d['excerpt'][:80]} for d in inputs['retrieved_documents']]
            return {'choices':[{'message':{'content':json.dumps({'decisions':decisions})}}]}
        return super().chat(messages,max_tokens)


def replay(trace,accept):
    session,calls=_load(trace);client=FixtureReplay(session,calls,accept)
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    old=e2_rag_selection.install(store)
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:e2_rag_selection.restore(old);store.close()
    events=e2_rag_selection.LAST_RUN['events']
    if any(e['event']=='selection_failed' for e in events):raise AssertionError('selector fixture failed')
    if client.remaining:raise AssertionError('unconsumed saved responses')
    return {'trace_name':Path(trace).parent.name,'synthetic_accept':accept,
            'remaining':client.remaining,'synthetic_selector_calls':client.selector_calls,
            'selected_counts':[len(e['accepted_ids']) for e in events if e['event']=='selection_completed'],
            'meaning':'synthetic selector + saved Doctor responses; integration only, no quality measurement'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+');args=p.parse_args()
    print(json.dumps([replay(t,a) for t in args.traces for a in (False,True)],ensure_ascii=False,indent=2))
