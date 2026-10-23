"""Strict saved-session integration replay for coverage-order and control arms."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from replay_response_session import StrictClient
from replay_e2_session import _load,consult,prepare
from nova_agent import response_state,coverage_order,e2_rag_selection
from nova_agent.rag_retrieval import VectorStore


def replay(path):
    manifest=json.loads((path.parent/'manifest.json').read_text())
    session,calls=_load(path);client=StrictClient(session,calls);events=[]
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    r=e2_rag_selection.install(store);s=response_state.install(events)
    o=coverage_order.install(events) if manifest['mode']=='R3a_coverage_order' else None
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:
        if o is not None:coverage_order.restore(o)
        response_state.restore(s);e2_rag_selection.restore(r);store.close()
    if client.remaining:raise AssertionError('saved responses left unused')
    return {'run':path.parent.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'remaining':client.remaining,'all_model_inputs_actions_and_final_note_match':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    result={'scope':'strict saved-response integration replay, not a score or clinical effect test',
            'runs':[replay(path) for path in a.traces]}
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
