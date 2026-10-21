"""Check deterministic final P completion formatting on real saved notes.
No model/patient API calls; not represented as new submitted SOAP or a score.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from nova_agent.e2_safety_delivery import reconcile_education
from nova_agent.safety_trace import SafetyTimeline


def main():
    rows=[]
    for p in sorted((ROOT/'results').glob('20261022_*_safety_session_*/timeline.json')):
        data=json.loads(p.read_text())
        if not data.get('final'):continue
        before=deepcopy(data['final']['note']);source=deepcopy(before)
        if '실제 전달 확인(성공 SAY):' in source['P'].get('education',''):
            source['P']['education']=source['P']['education'].split('실제 전달 확인(성공 SAY):',1)[0].removeprefix('교육 계획(실제 수행은 아래 성공 발화에 한함):').strip()
        frozen=deepcopy(source);timeline=SafetyTimeline();timeline.speech=data['successful_speech'];timeline.records=data['records']
        after=reconcile_education(source,timeline)
        assert source==frozen
        assert all(after.get(k)==source.get(k) for k in ('S','O','A'))
        for field,value in source.get('P',{}).items():
            if field!='education':assert re.findall(r'\d+',value)==re.findall(r'\d+',after['P'][field])
        actual=[s['content'] for s in timeline.speech if s['record_count']>0 and '?' not in s['content']]
        performed=after['P']['education'].split('실제 전달 확인(성공 SAY):',1)[1]
        assert all(text in performed for text in actual)
        plans=' '.join(v for k,v in after['P'].items() if k!='education')+' '+after['P']['education'].split('실제 전달 확인(성공 SAY):',1)[0]
        assert not re.search(r'(?:설명|안내|교육)(?:했다|함|하였음|했고)',plans)
        rows.append({'run':p.parent.name,'unchanged_S_O_A':True,'unchanged_non_education_numeric_tokens':True,
                     'actual_speech_echoed':True,'input_note_not_mutated':True,
                     'changed_other_P_fields':[k for k in source['P'] if k!='education' and source['P'][k]!=after['P'][k]]})
    result={'scope':'deterministic formatting replay on saved final notes; NO new API submission, clinical entailment or score claim','checked_sessions':len(rows),'results':rows}
    (ROOT/'reports/completion_format_replay_041.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'checked_sessions':len(rows),'passed':True}))

if __name__=='__main__':main()
