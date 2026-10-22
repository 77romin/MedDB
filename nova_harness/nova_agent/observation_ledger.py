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
patient_context의 진료 대상과 답변하는 보호자를 구분하세요. 진료 대상 아이는 patient이며
그 아이의 부모 증상은 family입니다. 주어가 불명확하면 unknown으로 남깁니다.
원문에 없는 관찰을 만들지 마세요. 다른 증상에 대한 부정으로 질문 증상을 부정하지 마세요.
가족/타인의 증상과 환자 본인을 구분하고 과거·현재·조건부를 분리하세요.
예/아니요 접두만으로 판단하지 말고 정정·부분 부정·빈도·기간을 보존하세요.
거의 없다/자주는 아니다는 절대 부재가 아닙니다. 약을 먹을 때/안 먹을 때 상태는 별개입니다.
복합 개념 중 일부만 답하면 scope=partial, 답하지 않은 내용은 만들지 않습니다.
"네/아니요"만의 답은 질문 대상·주어·시점·의미가 명확할 때만 해석합니다.
각 quote는 실제 response의 연속 원문으로 주어·시점·부정 범위를 충분히 포함해야 합니다.
확실하지 않으면 assertion=uncertain, subject/temporality=unknown, scope=partial로 남기세요.
질문에 답을 받았는지와 환자 본인의 현재 증상 여부는 별개입니다.
예: 부모님 과거력 질문에 부모님에 대한 명확한 답이면 family/past 관찰로 답변 완료이나
환자 현재 소견을 채우지 않습니다. 질문의 대상/시점/범위를 답변과 비교해 answer_contract를 적습니다.
quote는 답변 원문이며 status=complete는 질문한 내용에 충분히 답한 경우에만 씁니다.
JSON만 출력: {"answer_contract":{"subject":"patient|family|other|unknown",
"temporality":"current|past|conditional|unknown","status":"complete|partial|unknown",
"quote":"응답 원문"},"facts":[{"concept_id":"후보 id","evidence_id":"현재 evidence id",
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
        self.answer_status={}

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
            # Preserve question-relative completeness, separately from eligibility
            # for an unqualified patient-current binary projection.
            row=deepcopy(p)
            projectable=row['scope']=='full' and not any(q['name'] in ('frequency','condition') for q in qualifiers)
            accepted,errors=self.state.accept_facts([row]);rejected.extend(errors)
            for f in accepted:
                f.update(scope=row['scope'],binary_projectable=projectable,qualifiers=deepcopy(qualifiers),replaces=list(replaces),
                         correction_quote=correction)
                valid.append(f)
        self._answer_contract(payload.get('answer_contract'),evidence,valid)
        self.events.append({'event':'observation_validated','evidence_id':evidence.id,
                            'accepted':len(valid),'rejected':len(rejected),'rejection_reasons':list(rejected)})
        return valid,rejected

    def _answer_contract(self,contract,evidence,valid):
        if not evidence.target:return
        status='unknown';subject='unknown';temporality='unknown'
        if (isinstance(contract,dict) and contract.get('status') in ('complete','partial','unknown')
            and contract.get('subject') in ('patient','family','other','unknown')
            and contract.get('temporality') in ('current','past','conditional','unknown')
            and isinstance(contract.get('quote'),str) and contract['quote'].strip()
            and contract['quote'] in evidence.response):
            subject=contract['subject'];temporality=contract['temporality'];status=contract['status']
            supported=any(f['concept_id']==evidence.target and f['scope']=='full'
                          and f['subject']==subject and f['temporality']==temporality
                          and f['assertion'] in ('present','absent') for f in valid)
            if status=='complete' and (not supported or subject=='unknown' or temporality=='unknown'):
                status='partial'
        self.answer_status[evidence.target]={'status':status,'subject':subject,
                    'temporality':temporality,'evidence_id':evidence.id}
        self.events.append({'event':'answer_contract','evidence_id':evidence.id,'status':status})

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
            source={'patient_context':self.state.initial,'evidence_id':evidence.id,'question':question,'response':response,'target':target,
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

    def _reduce(self,eligible):
        replaced={i for f in self.state.facts for i in f.get('replaces',[])}
        active=defaultdict(list)
        for f in self.state.facts:
            if f['id'] not in replaced and f.get('binary_projectable',False) and eligible(f):
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

    def current_view(self):
        return self._reduce(lambda f:f['subject']=='patient' and f['temporality']=='current')

    def view(self):
        # A family-history concept is ABOUT relatives, not the patient's current
        # symptom. Existing ontology SOAP metadata defines those feature scopes.
        def eligible(f):
            row=self.db.findings[f['concept_id']]
            if row['kind']=='history' and row.get('soap')=='S.가족력':
                return f['subject']=='family' and f['temporality'] in ('past','current')
            if row['kind']=='history' and row.get('soap') in ('S.과거력','S.알레르기'):
                return f['subject']=='patient' and f['temporality'] in ('past','current')
            return f['subject']=='patient' and f['temporality']=='current'
        return self._reduce(eligible)

    def snapshot(self):
        # Do not use PatientState.snapshot's broader generic "covered" count:
        # family/past observations here explicitly do not fill current state.
        view,conflicts=self.view()
        return {'evidence':[vars(e) for e in self.state.evidence],'facts':deepcopy(self.state.facts),
                'current_patient_view':self.current_view()[0],'kb_feature_view':view,'answer_status':deepcopy(self.answer_status),
                'conflicts':sorted(conflicts),'failures':list(self.failures)}
