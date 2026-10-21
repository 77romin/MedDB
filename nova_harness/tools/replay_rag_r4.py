"""Assert R3c/R4 exact API request parity with saved responses, not scores."""
from copy import deepcopy
import json
from pathlib import Path
from replay_rag_r3b import QueryFixtureReplay, _load, consult, prepare, ROOT, VectorStore
from nova_agent import e2_rag_generation, rag_graph
from nova_agent.rag_generation import SYSTEM

class Capture(QueryFixtureReplay):
    def __init__(self,*args):super().__init__(*args);self.requests=[]
    def chat(self,messages,max_tokens):
        self.requests.append(deepcopy((messages,max_tokens)))
        messages=deepcopy(messages)
        if messages[0]['content'].endswith(SYSTEM):messages[0]['content']=messages[0]['content'][:-len(SYSTEM)]
        return super().chat(messages,max_tokens)

def run(trace,valid,module):
    session,calls=_load(trace);client=Capture(session,calls,valid)
    store=VectorStore(ROOT/'dist/rag/index.sqlite',ROOT/'vendor/guidelines/guidelines')
    old=module.install(store)
    try:consult(client,prepare(),knowledge_mode='clinical',reference_profile='reviewed')
    finally:module.restore(old);store.close()
    assert client.remaining==0
    return client.requests,client.seen

if __name__=='__main__':
    traces=[ROOT/'results'/name/'trace.jsonl' for name in ('20261020_004440_598870_meddb_e2_ledger','20261020_004936_372121_meddb_e2_ledger','20261020_004937_808955_meddb_e2_ledger')]
    results=[]
    for trace in traces:
        for valid in (False,True):
            a=run(trace,valid,e2_rag_generation);b=run(trace,valid,rag_graph)
            assert a==b,(trace,valid,'request mismatch')
            results.append({'trace_name':trace.parent.name,'synthetic_valid':valid,'identical_requests':len(a[0]),'identical_actions':True,'nodes':rag_graph.LAST_RUN['nodes']})
    print(json.dumps(results,ensure_ascii=False,indent=2))
