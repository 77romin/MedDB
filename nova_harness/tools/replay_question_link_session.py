"""Strict full-session replay through the new linker, with saved model replies.

Passing shows unchanged requests/actions/notes on this recorded path, not new
clinical performance. New branches require actual live or explicit fixture tests.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from replay_response_session import StrictClient
from replay_e2_session import _load,consult,prepare
from nova_agent import response_state,coverage_order,e2_question_link,e2_rag_selection
from nova_agent.rag_retrieval import VectorStore


def replay(path):
    session,calls=_load(path);client=StrictClient(session,calls);events=[]
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    r=e2_rag_selection.install(store);s=response_state.install(events)
    o=coverage_order.install(events);l=e2_question_link.install(events)
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:
        e2_question_link.restore(l);coverage_order.restore(o)
        response_state.restore(s);e2_rag_selection.restore(r);store.close()
    if client.remaining:raise AssertionError('saved responses left unused')
    return {'run':path.parent.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'remaining':0,'all_model_inputs_actions_and_final_note_match':True,
            'link_event_counts':dict(Counter(e['event'] for e in events if e['event'].startswith('question_link'))),
            'abstention_reasons':dict(Counter(e['reason'] for e in events if e['event']=='question_link_abstained'))}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'strict full-session saved-response replay through the new linker; no score',
       'sessions':[replay(path) for path in a.traces]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
