"""Isolated extracted artifact replay; private traces never enter the ZIP."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
DRIVER=r'''
from copy import deepcopy
import json,sys
from pathlib import Path
import run
from nova_sdk import NovaError
class ReplayMismatch(BaseException):pass
def require(condition, message):
    if not condition:raise ReplayMismatch(message)
rows=[json.loads(l) for l in Path(sys.argv[1]).read_text().splitlines()]
responses={r.get('request_id'):r['response'] for r in rows if r['event']=='http_response'}
errors={r.get('request_id'):r for r in rows if r['event']=='http_error'}
session=next(r['response'] for r in rows if r['event']=='http_response' and isinstance(r.get('response'),dict) and r['response'].get('initial'))
session=deepcopy(session);session['deadline']='2099-01-01T00:00:00+00:00'
calls=[]
for r in rows:
    if r['event']!='http_request':continue
    b=r.get('body')or{}
    if r['path']=='/v1/chat/completions' or r['path'].endswith('/actions'):
        calls.append((b,responses.get(b.get('request_id')),errors.get(b.get('request_id'))))
class Client:
    submitted=False
    def session(self):return deepcopy(session)
    def pop(self,kind):
        require(bool(calls),'unexpected extra request')
        b,response,error=calls.pop(0)
        require((b.get('action')or'CHAT').lower()==kind,'action order differs')
        return b,response,error
    def result(self,r,e):
        if e and r is None:raise NovaError(e['code'],e.get('status'))
        return deepcopy(r)
    def chat(self,messages,max_tokens,**kwargs):
        b,r,e=self.pop('chat');require(b['messages']==messages and b['max_tokens']==max_tokens,'model input differs')
        return self.result(r,e)
    def say(self,content,**kwargs):
        b,r,e=self.pop('say');require(b['content']==content,'SAY differs');return self.result(r,e)
    def exam(self,content,**kwargs):
        b,r,e=self.pop('exam');require(b['content']==content,'EXAM differs');return self.result(r,e)
    def diagnose(self,note,diagnosis,**kwargs):
        b,r,e=self.pop('diagnose');require(b['note']==note and b['diagnosis']==diagnosis,'final SOAP differs')
        self.submitted=True;return self.result(r,e)
db=run.prepare()
c=Client()
try:run.consult(c,db)
finally:
    if hasattr(db,'rag_store'):db.rag_store.close()
require(not calls and c.submitted,'unused requests or missing final submission')
print('ARTIFACT_REPLAY_OK')
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('zip',type=Path);p.add_argument('traces',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(a.zip) as z:z.extractall(tmp)
        for trace in a.traces:
            env=dict(os.environ,NOVA_GUIDELINES_DIR=str(Path(__file__).resolve().parents[1]/'vendor/guidelines/guidelines'))
            r=subprocess.run([sys.executable,'-c',DRIVER,str(trace.resolve())],cwd=tmp,env=env,capture_output=True,text=True)
            if r.returncode or 'ARTIFACT_REPLAY_OK' not in r.stdout:
                raise RuntimeError('Artifact replay failed: '+r.stderr[-1800:])
            results.append({'run':trace.parent.name,'extracted_zip_model_inputs_actions_and_final_note_match':True})
    out={'scope':'isolated ZIP replay of saved development sessions; no network or official score','sessions':results}
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
if __name__=='__main__':main()
