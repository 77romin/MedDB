"""Synthetic query/selector integration replay, never a performance estimate."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from replay_rag_r3a import FixtureReplay, _load, consult, prepare
from nova_agent import e2_rag_query
from nova_agent.rag_query import SYSTEM
from nova_agent.rag_retrieval import VectorStore


class QueryFixtureReplay(FixtureReplay):
    def __init__(self,session,calls,valid):
        super().__init__(session,calls,valid);self.valid=valid;self.query_calls=0

    def chat(self,messages,max_tokens):
        if messages[0]['content']==SYSTEM:
            self.query_calls+=1
            data=json.loads(messages[1]['content']);evidence=data['patient_observations'][0]
            result={'query':data['hypotheses_query'][:220].strip()+' followup', 'intent':'follow_up',
                    'clinical_question':'Synthetic integration question, not a clinical decision',
                    'patient_evidence':[{'id':evidence['id'],'quote':evidence['content'][:80]}]}
            if not self.valid:result['patient_evidence'][0]['id']='invented'
            return {'choices':[{'message':{'content':json.dumps(result)}}]}
        return super().chat(messages,max_tokens)


def replay(trace,valid):
    session,calls=_load(trace);client=QueryFixtureReplay(session,calls,valid)
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    old=e2_rag_query.install(store)
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:e2_rag_query.restore(old);store.close()
    if client.remaining:raise AssertionError('unconsumed saved responses')
    return {'trace_name':Path(trace).parent.name,'synthetic_query_valid':valid,
            'remaining':client.remaining,'synthetic_query_calls':client.query_calls,
            'synthetic_selector_calls':client.selector_calls,
            'query_event_types':[e['event'] for e in e2_rag_query.LAST_RUN['events']],
            'meaning':'synthetic query and selector + saved Doctor responses; integration only'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+');args=p.parse_args()
    print(json.dumps([replay(t,v) for t in args.traces for v in (False,True)],ensure_ascii=False,indent=2))
