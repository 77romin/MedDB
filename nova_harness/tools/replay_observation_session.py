"""Strict saved full-session replay with typed observation calls and final note."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from replay_e2_session import _load,consult,prepare
from replay_response_session import StrictClient
from nova_agent import response_state,coverage_order,e2_observation_state,e2_rag_selection,model_question_policy
from nova_agent.rag_retrieval import VectorStore

class Replay(StrictClient):
    def chat(self,messages,max_tokens,**kwargs):
        row=self._pop('chat')
        if messages!=row['messages'] or max_tokens!=row['max_tokens']:
            raise AssertionError('saved model input differs')
        self.seen.append(('chat',max_tokens));return deepcopy(row['response'])


def replay(path):
    m=json.loads((path.parent/'manifest.json').read_text());session,calls=_load(path)
    client=Replay(session,calls);events=[];ledgers=[]
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    r=e2_rag_selection.install(store);s=response_state.install(events);o=coverage_order.install(events)
    u=e2_observation_state.install(events,ledgers) if m['mode'] in ('R3a_observation_state','R3a_model_questions') else None
    q=model_question_policy.install(events) if m['mode']=='R3a_model_questions' else None
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:
        if q is not None:model_question_policy.restore(q)
        if u is not None:e2_observation_state.restore(u)
        coverage_order.restore(o);response_state.restore(s);e2_rag_selection.restore(r);store.close()
    if client.remaining:raise AssertionError('saved model replies unused')
    if any(l.failures for l in ledgers):raise AssertionError('strict replay contains extraction failure/input drift')
    return {'run':path.parent.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'all_model_inputs_actions_and_final_note_match':True,'remaining':0,
            'observed_sources':sum(len(l.state.evidence) for l in ledgers),
            'validated_facts':sum(len(l.state.facts) for l in ledgers)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'strict saved full-session replay; not new patient/model or official scoring runs',
       'sessions':[replay(path) for path in a.traces]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
