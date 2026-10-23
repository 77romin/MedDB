"""Re-run actual failed S2 planner outputs and answered questions without API calls."""
from collections import Counter
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor/meddb')]
from examples.hybrid_agent import parse_json
from nova_agent.safety_obligations import ObligationLedger
from nova_agent.answered_questions import answered,question_key


def main():
    summary=json.loads((Path(sys.argv[1])/'summary.json').read_text());results=[]
    for item in summary['runs']:
        out=Path(item['directory']);trace=[json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
        for i,row in enumerate(trace):
            body=row.get('body',{});messages=body.get('messages',[]) if isinstance(body,dict) else []
            if not messages or not messages[0].get('content','').startswith('기존 계획 자료에서 환자에게'):continue
            response=next(r for r in trace[i+1:] if r['event']=='http_response')
            payload=parse_json(response['response']['choices'][0]['message']['content'] or '')
            note={'P':json.loads(messages[-1]['content'])['source_plan']}
            strict_valid=[]
            for candidate in payload['obligations']:
                ledger=ObligationLedger();ledger.update(note)
                try:strict_valid+=ledger.register({'obligations':[candidate]})
                except ValueError:pass
            ledger=ObligationLedger();ledger.update(note);accepted,rejected=ledger.register_partial(payload)
            assert {r['id'] for r in strict_valid}=={r['id'] for r in accepted}
            assert all(r['state']=='generated' for r in accepted)
            speech=json.loads((out/'timeline.json').read_text())['successful_speech'];seen={};would_block=0
            for s in speech:
                if s['record_count']>0:continue
                key=question_key(s['content'])
                if '?' in s['content'] and key in seen:would_block+=1
                answer=s.get('reply',{}).get('content','')
                if '?' in s['content'] and answered(answer):seen[key]=answer
            results.append({'case':item['case_label'],'accepted_complete_items':len(accepted),
                            'rejected_items':len(rejected),'unresolved_reasons':dict(Counter(r['reason'] for r in rejected)),
                            'same_question_candidates_with_prior_nonambiguous_answer':would_block,
                            'new_patient_actions':0})
    report={'scope':'saved real outputs only, not a fresh session or score','runs':results}
    (ROOT/'reports/replay_044.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
