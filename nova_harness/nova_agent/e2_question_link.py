"""Version-checked E2 fallback for free questions; canonical/pick paths unchanged.

Resolve target before the existing allow_action and API request. Only the original
successful say() path records the reply and invokes existing answer interpretation.
No failed or proposed question is recorded as an observed medical fact.
"""
from pathlib import Path
import types
from .question_link import propose,signature

OLD='''                target = next((fid for fid, row in {**db.slots, **db.findings}.items()
                               if row.get('ask') and norm(row['ask']) == norm(text)), None)
'''
NEW=OLD+'''                if target is None:
                    target = _link_free_question(care, text)
'''


def patched_source(source):
    if source.count(OLD)!=1:raise ValueError('Unexpected E2 free-question linking contract')
    return source.replace(OLD,NEW)


def install(events):
    from examples import hybrid_care,hybrid_comm
    from meddb import coverage
    original_class=coverage.CareCoverage
    original_consult=hybrid_care.base_consult
    source=Path(hybrid_comm.__file__).read_text(encoding='utf-8')
    module=types.ModuleType('examples.hybrid_comm_question_link')
    module.__file__=hybrid_comm.__file__
    exec(compile(patched_source(source),module.__file__,'exec'),module.__dict__)
    module._link_free_question=lambda care,text:propose(care,text,events)
    class LinkedCoverage(original_class):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self._pending_question_links={}
            self.question_link_observations=[]
        def observe(self,target,question,answer,turn):
            super().observe(target,question,answer,turn)
            # say() may prepend one fixed empathy phrase; preserve actual wording
            # in the original response history, only normalize that known prefix.
            normalized=question
            if normalized.startswith(hybrid_comm.EMPATHY):normalized=normalized[len(hybrid_comm.EMPATHY):]
            metadata=self._pending_question_links.pop((target,signature(normalized)),None)
            if metadata:
                self.question_link_observations.append({'target':target,'question':question,
                         'answer':answer,'turn':turn,**metadata})
                events.append({'event':'question_link_observed','target':target,'turn':turn,**metadata})
        def allow_action(self,kb,kind,text,target):
            # The caller supplies the recovered target. Preserve the exact same
            # original eligibility/duplicate rules, including the response guard.
            allowed=super().allow_action(kb,kind,text,target)
            if not allowed:
                self._pending_question_links.pop((target,signature(text)),None)
            return allowed
        def trace(self):
            data=super().trace();data['question_link_observations']=self.question_link_observations
            return data
    coverage.CareCoverage=LinkedCoverage
    hybrid_care.base_consult=module.consult
    return original_consult,original_class


def restore(previous):
    from examples import hybrid_care
    from meddb import coverage
    hybrid_care.base_consult,coverage.CareCoverage=previous
