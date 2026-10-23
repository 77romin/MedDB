"""Paid offline counterexample authoring. Never imported by the consultation runtime."""
import json
import os
from pathlib import Path
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.experiment import load_local_env
from nova_agent.protocol import Gateway, LoggedClient
from nova_agent.config import Config
from nova_agent.telemetry import Trace
from nova_agent.validation import parse_object

PROMPT='''NOVA 에이전트의 근거 추출을 검증할 합성 연습자료를 작성합니다. 실제 환자나 대회 증례가 아닙니다.
환자 답변의 값·단위·시간과 질문의 값이 다른 반례, 일부만 대답한 경우, 모른다는 답, 비교 부정, 가족/본인 구분을 포함합니다.
공개/비공개 증례 ID나 정답을 쓰지 않습니다. 임상 처방·권고가 아니라 데이터 추출 검증입니다.
JSON 하나: {"scope":"synthetic_extraction_counterexamples_not_clinically_validated","cases":[{"id":"synthetic_01","question":"한 가지 질문","response":"합성 답변","proposed_fact":{"concept_id":"test:observation","evidence_id":"e1","quote":"답변 부분문자열","assertion":"present|absent|unknown","attribute":"dose_count|strength|frequency|last_dose|duration","value":"실제 문자열","unit":"선택적 실제 문자열","time_anchor":"선택적 실제 문자열"},"expected_accept":true,"reason":"근거 검증의 이유"}]}
12개를 작성하고 절반은 거절해야 할 제안으로 합니다. 거절 사례는 원문에 없는 value/unit/time, 질문에서 빌린 값, unknown을 양성으로 만드는 것으로 구성합니다. 빈 선택 필드는 생략합니다. 단순 인용 일치가 의미를 보증하지 않는 반례는 별도로 reason에 한계를 명시합니다.'''

def main():
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise ValueError('NOVA_DEV_KEY missing')
    directory=ROOT/'results'/datetime.now().strftime('%Y%m%d_%H%M%S_counterexamples')
    directory.mkdir(parents=True)
    trace=Trace(directory/'trace.jsonl',secrets=[key])
    client=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    cfg=Config(model='openai/gpt-6.1-sol',record_tokens=6000)
    result=Gateway(client,cfg,trace).chat([{'role':'system','content':PROMPT}],final=True)
    value=parse_object(result['choices'][0]['message']['content'])
    if value.get('scope')!='synthetic_extraction_counterexamples_not_clinically_validated' or not isinstance(value.get('cases'),list):
        raise ValueError('invalid synthetic response')
    (directory/'counterexamples.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    (directory/'usage.json').write_text(json.dumps(result.get('usage',{})))
    print(directory)

if __name__=='__main__':main()
