"""Reproduce a real closing-output loss with the SAME saved Doctor response.
No API calls, no diagnosis scoring, no fabricated patient response.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from examples import hybrid_comm as C
from examples.hybrid_care import prepare
from nova_agent.safety_trace import SafetyTimeline
from nova_agent import e2_safety_delivery


def main():
    folder=ROOT/'results/20261021_231143_191528_meddb_e2_rag_graph'
    rows=[json.loads(line) for line in (folder/'trace.jsonl').read_text().splitlines()]
    requests={(r.get('body') or {}).get('request_id'):r.get('body') or {} for r in rows if r.get('event')=='http_request'}
    response=next(r['response'] for r in rows if r.get('event')=='http_response' and
        (requests.get(r.get('request_id'),{}).get('messages') or [{}])[0].get('content','').startswith('외래 진료를 마무리'))
    final=next(body for body in reversed(list(requests.values())) if body.get('action')=='DIAGNOSE')
    class Saved:
        calls=0
        def chat(self,*args,**kwargs):self.calls+=1;return deepcopy(response)
        def session(self):return {'deadline':'2099-01-01T00:00:00+00:00','turns_remaining':12}
    db=prepare();client=Saved()
    baseline=C._closing_sentences(client,db,final['note'],final['diagnosis'],'걱정돼요.',True)
    original=e2_safety_delivery.install(SafetyTimeline())
    try:improved=C._closing_sentences(client,db,final['note'],final['diagnosis'],'걱정돼요.',True)
    finally:e2_safety_delivery.restore(original)
    warning=json.loads(response['choices'][0]['message']['content'])['safety']
    expected=warning.split('. ');expected=[s if s.endswith('.') else s+'.' for s in expected]
    assert len(expected)==2 and all(part in improved for part in expected)
    assert all(part not in baseline for part in expected)
    assert client.calls==2
    result={'scope':'same real saved Doctor response; delivery proposals only, no new patient interaction or score',
        'baseline_generic_safety':True,'candidate_preserved_complete_warning_sentences':len(expected),
        'preserved_sentence_lengths':[len(s) for s in expected],
        'baseline_message_count':len(baseline),'candidate_message_count':len(improved),
        'additional_model_calls':0,'all_candidate_messages_within_30':all(len(s)<=30 for s in improved)}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
