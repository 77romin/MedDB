"""Use only actual initial information and successful action responses from the SDK."""
from meddb import KB


class KnowledgeSession:
    def __init__(self,kb=None,profile='reviewed',phase='preliminary'):
        self.kb=kb or KB();self.profile=profile;self.phase=phase
        self.events=[];self.observations={};self.patient={};self.patient_evidence={};self.history={}

    def record_result(self,kind,turn,content):
        event_id=f'{kind}-{turn}'
        self.events.append({'id':event_id,'kind':kind,'turn':turn,'content':content})
        return event_id

    def confirm_observation(self,finding_id,state,evidence_ids):
        # The caller verifies the semantic mapping; merely asking a question is insufficient.
        self.observations[finding_id]={'finding_id':finding_id,'state':state,'evidence_ids':evidence_ids}

    def confirm_patient_field(self,field,value,evidence_ids):
        self.patient[field]=value;self.patient_evidence[field]=evidence_ids

    def complete_history(self,requirement,value,evidence_id):
        self.history[requirement]={'status':'confirmed','value':value,'evidence_id':evidence_id}

    def support(self):
        return self.kb.assist(list(self.observations.values()),self.events,self.patient,self.patient_evidence,self.history,self.profile,self.phase)
