"""Small, reversible E2 extension. Upstream files remain unchanged.

Adds dose-reconciliation questions only after medication use is observed, and repairs
closing sentences against the patient's actual plan. No sample IDs or answers.
"""
import json

from nova_sdk import NovaError
from .closing import PROMPT, short_statement
from .validation import parse_object


def install():
    import meddb.coverage as coverage
    from examples import hybrid_comm as comm
    from examples import hybrid_agent as hybrid
    original_coverage = coverage.CareCoverage

    class ExtendedCoverage(original_coverage):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.extra.update({
                'med_strength':('그 약 한 알은 몇 mg인가요?','pmh'),
                'med_last_taken':('그 약을 마지막으로 드신 때는 언제인가요?','pmh'),
                'med_total_24h':('지난 24시간에 그 약을 모두 몇 알 드셨나요?','pmh')})

        def needed(self,kb):
            actions=super().needed(kb)
            if 'hypnotic_use' not in kb.present:
                return actions
            for action in actions:
                if action['target']=='med_name': action['priority']=0.4
            for index,target in enumerate(('med_strength','med_last_taken','med_total_24h')):
                if target in self.records or self.attempts.get(target,0)>=2:
                    continue
                actions.append({'type':'SAY','text':self.extra[target][0],'target':target,'resolves':[],
                                'priority':0.5+index/10,'why':'확인된 약물의 실제 복용 내역 대조'})
            return sorted(actions,key=lambda a:a['priority'])

    original_closing=comm._closing_sentences

    def closing(client,db,note,diagnosis,concern,comprehensive=False):
        if not comprehensive:
            return original_closing(client,db,note,diagnosis,concern,comprehensive)
        keys=('assessment','plan','follow_up','safety_net','concern')
        payload={'diagnosis':diagnosis,'assessment':note.get('A',{}),'plan':note.get('P',{}),'concern':concern}
        result={}
        try:
            result=parse_object(hybrid.chat(client,PROMPT,json.dumps(payload,ensure_ascii=False),1536))
            invalid={k:result.get(k) for k in keys if not short_statement(result.get(k))}
            if invalid:
                fixed=parse_object(hybrid.chat(client,PROMPT+'\n각 항목은 반드시 문장 하나, 24자 이내로 다시 쓰세요.',
                    json.dumps({'invalid':invalid,'record':payload},ensure_ascii=False),1536))
                for key in invalid:
                    if short_statement(fixed.get(key)):result[key]=fixed[key]
        except (NovaError,ValueError,TypeError):
            pass
        sentences=[short_statement(result.get(k)) for k in keys]
        # Clinical content fallback remains upstream's conservative implementation.
        if not any(sentences):
            return original_closing(client,db,note,diagnosis,concern,True)
        if not concern or comm.NO_QUESTION.search(comm._nfc(concern)):
            sentences[-1]=None
        return [s for s in sentences if s]

    coverage.CareCoverage=ExtendedCoverage
    comm._closing_sentences=closing
    return {'coverage':original_coverage,'closing':original_closing}


def restore(original):
    import meddb.coverage as coverage
    from examples import hybrid_comm as comm
    coverage.CareCoverage=original['coverage']
    comm._closing_sentences=original['closing']
