"""Strict complete-session replay against saved R3a Doctor and patient responses.

All actions, model inputs, and final note must match. Passing demonstrates only
integration parity on this saved session; it cannot measure new question quality.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from replay_e2_session import ReplayClient,_load,consult,prepare
from nova_agent import e2_rag_selection,response_state
from nova_agent.rag_retrieval import VectorStore

class StrictClient(ReplayClient):
    def diagnose(self,note,diagnosis):
        expected=self._calls[0]
        if note!=expected['note'] or diagnosis!=expected['diagnosis']:
            raise AssertionError('final submitted note or diagnosis differs')
        return super().diagnose(note,diagnosis)

def replay(path):
    session,calls=_load(path);client=StrictClient(session,calls)
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    old_rag=e2_rag_selection.install(store);events=[];old=response_state.install(events)
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:response_state.restore(old);e2_rag_selection.restore(old_rag);store.close()
    if client.remaining:raise AssertionError('saved replies left unused')
    return {'run':path.parent.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'all_requests_and_final_note_match':True,'remaining':client.remaining,
            'observed_replies':sum(e['event']=='response_observed' for e in events)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);a=p.parse_args()
    print(json.dumps(replay(a.trace)))
