"""Saved-response integration replay. Not a new model run or score estimate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools'))
from replay_e2_session import ReplayClient, _load, consult, prepare
from nova_agent import e2_rag
from nova_agent.rag import VectorStore


class RagReplay(ReplayClient):
    def chat(self, messages, max_tokens):
        modified = messages[-1]['content'].startswith('[외부 지침 근거:')
        reference = messages[:-1] if modified else messages
        row = self._pop('chat')
        if reference != row['messages'] or row['max_tokens'] != max_tokens:
            raise AssertionError('unexpected change outside RAG context')
        self.seen.append(('chat', max_tokens))
        return deepcopy(row['response'])


def replay(trace):
    session, calls = _load(trace)
    client = RagReplay(session, calls)
    store = VectorStore(ROOT/'dist/rag/index.sqlite', ROOT/'vendor/guidelines/guidelines')
    old = e2_rag.install(store)
    try:
        consult(client, prepare(), knowledge_mode='clinical', reference_profile='reviewed')
    finally:
        e2_rag.restore(old)
        store.close()
    return {'trace_name': Path(trace).parent.name, 'remaining': client.remaining,
            'record_context_calls': (e2_rag.LAST_RUN or {}).get('injected_record_calls', 0),
            'retrieved': len((e2_rag.LAST_RUN or {}).get('retrieved', [])),
            'meaning': 'integration only; saved model responses cannot measure RAG benefit'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('traces', nargs='+')
    args = p.parse_args()
    print(json.dumps([replay(t) for t in args.traces], ensure_ascii=False, indent=2))
