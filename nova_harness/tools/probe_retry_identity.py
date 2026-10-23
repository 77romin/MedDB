"""Real development transport test: lose one acknowledged reply, retry SAME action ID.
No diagnosis/score evaluation. One logical greeting, two HTTP action attempts.
"""
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'vendor/meddb')]
from experiment import load_local_env
from nova_agent.protocol import LoggedClient
from nova_agent.telemetry import Trace
from nova_agent.safety_trace import TimelineClient,SafetyTimeline
from nova_sdk import NovaError
from examples.consult_skeleton import with_retry

def main():
    load_local_env();key=os.environ.get('NOVA_DEV_KEY','').strip()
    if not key:raise SystemExit('Key missing')
    out=ROOT/'results'/(datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S_%f')+'_retry_identity_probe');out.mkdir(mode=0o700)
    trace=Trace(out/'trace.jsonl',secrets=[key]);raw=LoggedClient(api_base='https://nova.snubhai.org',token=key,sample=True,trace=trace)
    before=raw.create_sample('4fa07144-04e5-4116-a18e-88d8a90cc21a')
    class LossOnce:
        def __init__(self):self.calls=0;self.ids=[]
        def say(self,content,*,request_id=None):
            self.calls+=1;self.ids.append(request_id)
            reply=raw.say(content,request_id=request_id)
            if self.calls==1:raise NovaError('INVALID_API_RESPONSE',502)
            return reply
    loss=LossOnce();timeline=SafetyTimeline();client=TimelineClient(loss,timeline)
    reply=with_retry(client.say,'안녕하세요.')
    after=raw.session()
    result={'scope':'controlled lost-reply transport test; no clinical assessment or score',
            'http_action_attempts':loss.calls,'same_nonempty_action_id':bool(loss.ids[0]) and len(set(loss.ids))==1,
            'server_turn_delta':before['turns_remaining']-after['turns_remaining'],
            'acknowledged_speech_count':len(timeline.speech),'simulated_failure_count':len(timeline.failures)}
    assert result['same_nonempty_action_id'] and result['server_turn_delta']==1 and len(timeline.speech)==1
    (ROOT/'reports/retry_identity_041.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
