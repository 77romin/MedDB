"""Development-only semantic consistency review; NOT an official/clinical score.

Uses no answer keys, public scripts, or case-specific ideal plans. Reviews only
what this agent planned, successfully said, and finally recorded. The stronger
model is a development reviewer, never the Doctor in a submission.
"""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from experiment import load_local_env
from nova_agent.protocol import LoggedClient
from nova_agent.telemetry import Trace

SYSTEM='''당신은 개발 실험의 기록-발화 일치 검토자입니다. 공식 채점이나 진단 정답 판정은 하지 않습니다.
주어진 실제 계획, 성공한 의사 SAY, 환자 응답, 최종 SOAP만 사용하세요. 일반 지식에서 이상적인 치료를 추가하지 마세요.
첫 기록의 P에 명시된 중요한 안전·추적·금지 행동 최대 10개를 독립 조건과 행동 단위로 나누세요.
각 항목이 실제 의사 SAY에 충분히 전달됐는지와 최종 P에 보존됐는지 판단하세요. 환자가 자발적으로 말한 행동을 의사가 설명한 것으로 간주하지 않습니다.
'심해지면 진료'는 특정 위험 증상 및 즉시 응급실 대응을 다 전달한 것으로 보지 않습니다. 부정·조건·시점이 달라지면 구분하세요.
교육 필드의 '설명함/안내함'이 실제 의사 발화로 지지되는지도 검사하세요. 기록만으로 부족하면 uncertain입니다.
JSON: {"checks":[{"plan_ref":{"record_index":0,"field":"treatment|education|follow_up|disposition|tests","quote":"첫 기록의 정확한 인용"},"spoken_refs":[{"index":0,"quote":"실제 의사 SAY의 정확한 인용"}],"final_ref":{"field":"education|follow_up|treatment|disposition|tests","quote":"최종 P의 정확한 인용 또는 빈 문자열"},"delivery":"covered|partial|missing|contradicted|uncertain","final_consistency":"preserved|omitted|changed|uncertain","reason":"근거 있는 짧은 이유"}],"unspoken_completed_claims":[{"field":"education","quote":"최종 P의 정확한 인용","reason":"수행 완료 주장이 실제 의사 발화에 없는 이유"}]}
인용은 실제 문자열과 정확히 같아야 하며 의사 발화 index는 입력 성공 발화 index를 그대로 사용하세요. 최대 10개 checks·3개 수행 주장. 설명만 있고 근거가 없으면 단정하지 마세요.'''


def validate(payload,records,speech,final):
    if not isinstance(payload,dict):raise ValueError('invalid review')
    checks=payload.get('checks',[]);claims=payload.get('unspoken_completed_claims',[])
    if not isinstance(checks,list) or not checks or len(checks)>10:raise ValueError('invalid checks')
    if not isinstance(claims,list) or len(claims)>3:raise ValueError('invalid claims')
    lookup={s['index']:s for s in speech}
    for check in checks:
        ref=check['plan_ref'];idx=ref['record_index'];field=ref['field'];quote=ref['quote']
        if not isinstance(idx,int) or not 0<=idx<len(records) or not quote or quote not in records[idx]['note'].get('P',{}).get(field,''):raise ValueError('bad plan quote')
        if check['delivery'] not in ('covered','partial','missing','contradicted','uncertain'):raise ValueError('bad delivery category')
        if check['final_consistency'] not in ('preserved','omitted','changed','uncertain'):raise ValueError('bad final category')
        for s in check['spoken_refs']:
            if s['index'] not in lookup or not s['quote'] or s['quote'] not in lookup[s['index']]['content']:raise ValueError('bad spoken quote')
        if check['delivery']=='covered' and not check['spoken_refs']:raise ValueError('coverage without speech')
        f=check['final_ref']
        if f['quote'] and f['quote'] not in final['note'].get('P',{}).get(f['field'],''):raise ValueError('bad final quote')
    for claim in claims:
        if not claim['quote'] or claim['quote'] not in final['note'].get('P',{}).get(claim['field'],''):raise ValueError('bad completed claim')
    return payload


def main():
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();out=Path(a.directory)
    data=json.loads((out/'timeline.json').read_text(encoding='utf-8'))
    records=data['records'];speech=[s for s in data['successful_speech'] if s['record_count']>0]
    if not records or not data.get('final'):raise SystemExit('Completed instrumented session required')
    review_input={'records':[{'note':{'P':r['note'].get('P',{})}} for r in records],
                  'successful_speech':speech,'final':{'note':{'P':data['final']['note'].get('P',{})}}}
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Key missing')
    trace=Trace(out/'review_trace.jsonl',secrets=[key]);client=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    response=client.chat([{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(review_input,ensure_ascii=False)}],
                         max_tokens=6144,reasoning_effort='low',model='openai/gpt-6.1-sol')
    # Standard library JSON first; no partial semantic review accepted.
    content=response['choices'][0]['message']['content'] or ''
    try:payload=json.loads(content)
    except ValueError:
        content=content.strip().removeprefix('```json').removesuffix('```').strip();payload=json.loads(content)
    validate(payload,records,speech,data['final'])
    result={'scope':'development model consistency judgments; no official score; provenance checked, semantics not independently proven',
            'reviewer':'openai/gpt-6.1-sol','review':payload}
    (out/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    from collections import Counter
    print(json.dumps({'directory':str(out),'delivery':dict(Counter(c['delivery'] for c in payload['checks'])),
                      'final_consistency':dict(Counter(c['final_consistency'] for c in payload['checks'])),
                      'unspoken_completed_claims':len(payload['unspoken_completed_claims'])},ensure_ascii=False))

if __name__=='__main__':main()
