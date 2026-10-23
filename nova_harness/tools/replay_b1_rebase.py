"""Strict main-based B1/B1O1 replay; no Q1 or old-vendor imports."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];TEAM=ROOT.parent if (ROOT.parent/'examples/agent_b1.py').exists() else ROOT/'vendor/meddb-publish'
sys.path[:0]=[str(TEAM),str(ROOT)]
from nova_sdk import NovaError
from meddb import MedDB
from examples import agent_b1,agent_b1_observed

class Mismatch(BaseException):pass

def replay(path):
    rows=[json.loads(l) for l in path.read_text().splitlines()]
    if not any(r['event']=='experiment_complete' for r in rows):raise ValueError('incomplete session; replay only after completion')
    m=json.loads((path.parent/'manifest.json').read_text())
    responses={r.get('request_id'):r['response'] for r in rows if r['event']=='http_response'}
    errors={r.get('request_id'):r for r in rows if r['event']=='http_error'}
    session=next(r['response'] for r in rows if r['event']=='http_response' and isinstance(r.get('response'),dict) and r['response'].get('initial'))
    session=deepcopy(session);session['deadline']='2099-01-01T00:00:00+00:00';calls=[]
    for r in rows:
        if r['event']!='http_request':continue
        b=r.get('body')or{}
        if r['path']=='/v1/chat/completions' or r['path'].endswith('/actions'):
            calls.append((b,responses.get(b.get('request_id')),errors.get(b.get('request_id'))))
    class Client:
        submitted=False
        def session(self):return deepcopy(session)
        def pop(self,kind):
            if not calls:raise Mismatch('extra request')
            b,r,e=calls.pop(0)
            if (b.get('action')or'CHAT').lower()!=kind:raise Mismatch('action order differs')
            return b,r,e
        def result(self,r,e):
            if e and r is None:raise NovaError(e['code'],e.get('status'))
            return deepcopy(r)
        def chat(self,messages,max_tokens,**kw):
            b,r,e=self.pop('chat')
            if b['messages']!=messages or b['max_tokens']!=max_tokens:raise Mismatch('model input differs')
            return self.result(r,e)
        def say(self,content,**kw):
            b,r,e=self.pop('say')
            if b['content']!=content:raise Mismatch('SAY differs')
            return self.result(r,e)
        def exam(self,content,**kw):
            b,r,e=self.pop('exam')
            if b['content']!=content:raise Mismatch('EXAM differs')
            return self.result(r,e)
        def diagnose(self,note,diagnosis,**kw):
            b,r,e=self.pop('diagnose')
            if b['note']!=note or b['diagnosis']!=diagnosis:raise Mismatch('final note differs')
            self.submitted=True;return self.result(r,e)
    spec=importlib.util.spec_from_file_location('run',ROOT/'vendor/starter/run.py')
    starter=importlib.util.module_from_spec(spec);sys.modules['run']=starter;spec.loader.exec_module(starter)
    c=Client();(agent_b1 if m['mode']=='B1' else agent_b1_observed).consult(c,MedDB.open())
    if calls or not c.submitted:raise Mismatch('unused requests or missing final submission')
    return {'run':path.parent.name,'mode':m['mode'],'all_model_inputs_actions_and_final_note_match':True}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('traces',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    r={'scope':'strict saved-session replay; no new API or official scores','sessions':[replay(x) for x in a.traces]}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
