"""Versioned source plan -> whole speech groups -> acknowledged performance.

Reuses the obligation validator; extraction is a model subset, never completeness.
No generic substitute may discharge a specific source obligation.
"""
from copy import deepcopy
import json
from .safety_obligations import ObligationLedger, complete_message
from .e2_safety_obligations import SYSTEM
from .safety_trace import digest


class PlanDelivery:
    def __init__(self):
        self.ledger = ObligationLedger()
        self.events = []
        self.groups = []
        self.version = None

    def compile(self, note, payload, record_count):
        self.ledger.update(note, record_count=record_count)
        # A new compilation never inherits old generated messages or delivery.
        self.ledger.versions[-1]['obligations'] = []
        rows, rejected = self.ledger.register_partial(payload)
        self.version = digest(self.ledger.versions[-1]['plan'])
        self.groups = deepcopy(rows)
        for row in self.groups:
            row['plan_version'] = self.version
            row['record_count'] = record_count
        self.events.append({'event':'compiled','version':self.version,
                            'accepted':len(rows),'rejected':len(rejected),
                            'coverage_verified':False})
        return rows

    def schedule(self, budget):
        messages=[]
        for row in sorted(self.groups, key=lambda r:r['priority']!='critical'):
            if len(row['messages']) <= budget:
                messages.extend(row['messages']);budget-=len(row['messages'])
                row['scheduled']=True
            else:
                row['scheduled']=False
                self.events.append({'event':'group_unscheduled','id':row['id'],'reason':'turn_budget'})
        return messages

    def audit(self, note, speech):
        # Ignore upstream's appended completion/teachback text when detecting a
        # rewritten plan. Match only the source draft preceding that marker.
        plan={k:v.split('환자에게 설명함:',1)[0].strip()
              for k,v in note.get('P',{}).items() if isinstance(v,str)}
        # Education may contain teachback without an appended explanation.
        if 'education' in plan:plan['education']=plan['education'].split('이해 확인 답변:',1)[0].strip()
        changed=digest(plan)!=self.version
        rows=[]
        for group in self.groups:
            eligible=[s for s in speech if s.get('record_count')==group['record_count']]
            # Ordered acknowledgements are required, including duplicates.
            pos=0;matched=[]
            for text in group['messages']:
                found=next((i for i in range(pos,len(eligible)) if eligible[i]['content']==text),None)
                if found is None:break
                matched.append(eligible[found]['index']);pos=found+1
            delivered=not changed and len(matched)==len(group['messages'])
            rows.append(dict(deepcopy(group),state='sent_success' if delivered else 'unresolved',delivery_events=matched))
        return {'version':self.version,'plan_changed':changed,'groups':rows,
                'coverage_verified':False,'events':deepcopy(self.events)}

    def render(self,note,speech):
        out=deepcopy(note);audit=self.audit(note,speech)
        # Draft wording can contain historical completion verbs; retain it only
        # in an explicitly attributed proposal, never as performed education.
        for field,value in list(out.setdefault('P',{}).items()):
            if isinstance(value,str):
                draft=value.split('환자에게 설명함:',1)[0]
                draft=draft.split('이해 확인 답변:',1)[0].strip()
                out['P'][field]='계획 원안 인용(수행 여부 미확인):\n'+draft
        actual=[s for s in speech if s.get('record_count',0)>0 and '?' not in s['content']]
        lines=['실제 전달 기록(API 성공 기준; 이해 여부 미확인):']
        lines.extend('[발화 {}] {}'.format(s['index'],s['content']) for s in actual)
        if not actual:lines.append('확인된 전달 없음.')
        lines.append('현재 계획의 추출 항목 중 완결 전달 확인: {}/{}; 전체 임상 완전성 미검증.'.format(
            sum(r['state']=='sent_success' for r in audit['groups']),len(audit['groups'])))
        if audit['plan_changed']:lines.append('계획 변경 후 재설명 미확인: 이전 전달을 현재 계획 완료로 승계하지 않음.')
        out['P']['education']+='\n'+'\n'.join(lines)
        return out


def install(timeline):
    from examples import hybrid_comm as C, hybrid_agent as H, hybrid_care
    from examples.consult_skeleton import seconds_left
    previous=C._closing_sentences
    selected=hybrid_care.base_consult.__globals__
    previous_selected=selected.get('_closing_sentences')
    if not callable(previous_selected):raise ValueError('unsupported selected consult closing boundary')
    delivery=PlanDelivery();timeline.plan_delivery=delivery

    def closing(client,db,note,diagnosis,concern,comprehensive=False):
        if not comprehensive:return previous(client,db,note,diagnosis,concern,comprehensive)
        payload={'obligations':[]};session=client.session()
        if seconds_left(session)>=120:
            try:
                response=client.chat([
                    {'role':'system','content':SYSTEM+'\n추가 키 intro/concern은 각각 진단 설명/환자 걱정 답변의 30자 이내 완결 문장입니다. 계획 안내는 obligations에서만 작성합니다. 임의 추가하지 마세요.'},
                    {'role':'user','content':json.dumps({'source_plan':note.get('P',{}),'diagnosis':diagnosis,'patient_concern':concern},ensure_ascii=False)}
                ],max_tokens=3072,reasoning_effort='low')
                parsed=H.parse_json(response['choices'][0]['message']['content'] or '')
                if isinstance(parsed,dict):payload=parsed
            except Exception as exc:
                delivery.events.append({'event':'compile_failed','error':type(exc).__name__})
        else:delivery.events.append({'event':'compile_skipped','reason':'deadline'})
        try:delivery.compile(note,payload,len(timeline.records))
        except (ValueError,TypeError,KeyError) as exc:
            delivery.events.append({'event':'invalid_payload','reason':str(exc)})
            delivery.compile(note,{'obligations':[]},len(timeline.records))
        # All source groups are indivisible; leave the existing question/answer/
        # teachback reserve. No clipping and no generic safety replacement.
        budget=max(0,session.get('turns_remaining',0)-3)
        result=delivery.schedule(budget)
        for key in ('intro','concern'):
            text=payload.get(key)
            if key=='concern' and (not concern or C.NO_QUESTION.search(C._nfc(concern))):continue
            if complete_message(text) and len(result)<budget:result.append(text)
        return result
    C._closing_sentences=closing
    selected['_closing_sentences']=closing
    return previous,selected,previous_selected


def restore(previous):
    from examples import hybrid_comm as C
    original,selected,original_selected=previous
    C._closing_sentences=original
    selected['_closing_sentences']=original_selected


class Client:
    def __init__(self,client,timeline):self.client=client;self.timeline=timeline
    def __getattr__(self,name):return getattr(self.client,name)
    def diagnose(self,*,note,diagnosis,**kwargs):
        rendered=self.timeline.plan_delivery.render(note,self.timeline.speech)
        return self.client.diagnose(note=rendered,diagnosis=diagnosis,**kwargs)
