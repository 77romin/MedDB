"""Single append-only interpretation boundary for E2 patient observations.

Reuses PatientState/Evidence validation. Quotes prove provenance, not semantic
truth; subject/time/scope/assertion remain model interpretations. Only validated
patient/current/full observations contribute to the existing binary KB view.
"""
from collections import defaultdict
from copy import deepcopy
import json
from .state import PatientState

SYSTEM='''환자의 실제 답변을 구조화된 관찰로 분해합니다. 진단·치료·다음 질문을 생성하지 않습니다.
후보 개념은 질문 target과 원문 용어 매칭에서 얻은 후보일 뿐이며, 존재를 의미하지 않습니다.
원문에 없는 관찰을 만들지 마세요. 다른 증상에 대한 부정으로 질문 증상을 부정하지 마세요.
가족/타인의 증상과 환자 본인을 구분하고 과거·현재·조건부를 분리하세요.
예/아니요 접두만으로 판단하지 말고 정정·부분 부정·빈도·기간을 보존하세요.
거의 없다/자주는 아니다는 절대 부재가 아닙니다. 약을 먹을 때/안 먹을 때 상태는 별개입니다.
복합 개념 중 일부만 답하면 scope=partial, 답하지 않은 내용은 만들지 않습니다.
"네/아니요"만의 답은 질문 대상·주어·시점·의미가 명확할 때만 해석합니다.
각 quote는 실제 response의 연속 원문으로 주어·시점·부정 범위를 충분히 포함해야 합니다.
확실하지 않으면 assertion=uncertain, subject/temporality=unknown, scope=partial로 남기세요.
JSON만 출력: {"facts":[{"concept_id":"후보 id","evidence_id":"현재 evidence id",
"quote":"응답 원문","assertion":"present|absent|uncertain|unknown",
"subject":"patient|family|other|unknown","temporality":"current|past|conditional|unknown",
"scope":"full|partial","qualifiers":[{"name":"frequency|duration|condition|severity|time","quote":"동일 quote에 있는 원문"}],
"replaces":[],"correction_quote":""}]}
명시적 정정으로 이전 같은 개념의 현재 관찰을 대체할 때만 replaces에 이전 fact id를 넣고
correction_quote에 정정 진술 원문을 적습니다. 단순 상충을 임의로 해결하지 않습니다.
최대8개 관찰, 없으면 facts=[]입니다. 수치 환산·약물 용량 계산은 하지 않습니다.'''


class ObservationLedger:
    def __init__(self,db):
        self.db=db
        concepts={fid:{'kind':row['kind']} for fid,row in db.findings.items()
                  if row['kind'] in ('symptom','history')}
        self.state=PatientState(initial={},concepts=concepts)
        self.events=[]
        self.targets={}
        self.failures=[]

    def candidates(self,response,target=None):
        matched=self.db.match_findings(response)
        ids=[]
        for fid in [target]+[fid for k in ('present','absent','unknown') for fid in matched.get(k,[])]:
            if fid in self.state.concepts and fid not in ids:ids.append(fid)
        return ids[:16]

    def accept(self,payload,evidence,allowed):
        if not isinstance(payload,dict) or not isinstance(payload.get('facts'),list) or len(payload['facts'])>8:
            raise ValueError('invalid fact array')
        valid=[];rejected=[]
        for p in payload['facts']:
            if not isinstance(p,dict):rejected.append('invalid_row');continue
            if (p.get('concept_id') not in allowed or p.get('evidence_id')!=evidence.id
                or p.get('temporality') not in ('current','past','conditional','unknown')
                or not isinstance(p.get('quote'),str) or not p['quote'].strip()
                or p.get('scope') not in ('full','partial')
                or p.get('subject') not in ('patient','family','other','unknown')):
                rejected.append('invalid_scope_or_source');continue
            qualifiers=p.get('qualifiers',[])
            if (not isinstance(qualifiers,list) or len(qualifiers)>6 or any(
                    not isinstance(q,dict) or q.get('name') not in ('frequency','duration','condition','severity','time')
                    or not isinstance(q.get('quote'),str) or not q['quote'] or q['quote'] not in p.get('quote','') for q in qualifiers)):
                rejected.append('invalid_qualifier');continue
            replaces=p.get('replaces',[]);correction=p.get('correction_quote','')
            existing={f['id']:f for f in self.state.facts}
            if not isinstance(replaces,list) or len(replaces)>8 or any(not isinstance(i,str) for i in replaces):
                rejected.append('invalid_replacements');continue
            if replaces and (not isinstance(correction,str) or not correction.strip() or correction not in evidence.response
                   or any(i not in existing or any(existing[i].get(k)!=p.get(k) for k in ('concept_id','subject','temporality')) for i in replaces)):
                rejected.append('unsupported_correction');continue
            # A frequency/conditional assertion describes a qualified proposition.
            # Keep it for records, but do not collapse it into the unqualified
            # binary KB view. This is deliberately conservative in this stage.
            row=deepcopy(p)
            if any(q['name'] in ('frequency','condition') for q in qualifiers):
                row['scope']='partial'
            accepted,errors=self.state.accept_facts([row]);rejected.extend(errors)
            for f in accepted:
                f.update(scope=row['scope'],qualifiers=deepcopy(qualifiers),replaces=list(replaces),
                         correction_quote=correction)
                valid.append(f)
        self.events.append({'event':'observation_validated','evidence_id':evidence.id,
                            'accepted':len(valid),'rejected':len(rejected)})
        return valid,rejected

    def observe(self,client,question,response,target,turn,deadline=None):
        evidence=self.state.add_response('SAY',question,{'content':response,'turn':turn},target or '')
        if target:self.targets[target]=evidence.id
        allowed=self.candidates(response,target)
        if not allowed:
            self.events.append({'event':'observation_raw_only','evidence_id':evidence.id})
            return evidence
        try:
            if deadline:
                from examples.consult_skeleton import seconds_left
                if seconds_left({'deadline':deadline})<120:raise ValueError('protect_record_deadline')
            source={'evidence_id':evidence.id,'question':question,'response':response,'target':target,
                    'candidates':[{'id':i,'name':self.db.findings[i]['ko'],'question':self.db.findings[i]['ask']} for i in allowed],
                    'prior_facts':[f for f in self.state.facts if f['concept_id'] in allowed][-16:]}
            result=client.chat([{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(source,ensure_ascii=False)}],
                               max_tokens=2048,reasoning_effort='low')
            content=result['choices'][0]['message']['content'] or ''
            self.accept(json.loads(content.strip().removeprefix('```json').removesuffix('```').strip()),evidence,allowed)
        except Exception as exc:
            self.failures.append({'evidence_id':evidence.id,'reason':type(exc).__name__})
            self.events.append({'event':'observation_failed','evidence_id':evidence.id,'reason':type(exc).__name__})
        return evidence

    def view(self):
        replaced={i for f in self.state.facts for i in f.get('replaces',[])}
        active=defaultdict(list)
        for f in self.state.facts:
            if f['id'] not in replaced and f['subject']=='patient' and f['temporality']=='current' and f['scope']=='full':
                active[f['concept_id']].append(f)
        result={};conflicts=set()
        for fid,rows in active.items():
            values={f['assertion'] for f in rows if f['assertion'] in ('present','absent')}
            if len(values)>1:result[fid]='?';conflicts.add(fid)
            elif values:result[fid]='+' if 'present' in values else '-'
            else:result[fid]='?'
        for target in self.targets:
            if target in self.state.concepts:result.setdefault(target,'?')
        return result,conflicts

    def snapshot(self):
        # Do not use PatientState.snapshot's broader generic "covered" count:
        # family/past observations here explicitly do not fill current state.
        view,conflicts=self.view()
        return {'evidence':[vars(e) for e in self.state.evidence],'facts':deepcopy(self.state.facts),
                'current_patient_view':view,'conflicts':sorted(conflicts),'failures':list(self.failures)}
