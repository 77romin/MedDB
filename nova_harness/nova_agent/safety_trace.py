"""Private diagnostic timeline: actual records, successful speech, final SOAP.

This module never edits a request or a note and makes no extra model calls.
"""
from copy import deepcopy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class SafetyTimeline:
    def __init__(self, trace=None):
        self.trace = trace
        self.records = []
        self.speech = []
        self.failures = []
        self.final = None

    def record(self, opening, vitals, transcript, note, diagnosis):
        observation = deepcopy({'opening': opening, 'vitals': vitals, 'transcript': list(transcript)})
        row = {'index': len(self.records), 'observation_hash': digest(observation),
               'observation': observation, 'note': deepcopy(note), 'diagnosis': diagnosis,
               'successful_speech_count': len(self.speech)}
        self.records.append(row)
        if self.trace:self.trace.emit('safety_record', **row)

    def snapshot(self):
        return deepcopy({'records': self.records, 'successful_speech': self.speech,
                         'failed_actions': self.failures, 'final': self.final})


class TimelineClient:
    def __init__(self, client, timeline):self.client=client;self.timeline=timeline
    def __getattr__(self, name):return getattr(self.client, name)
    def say(self, content, **kwargs):
        try:reply=self.client.say(content, **kwargs)
        except Exception as exc:
            self.timeline.failures.append({'action':'SAY','content':content,'error':getattr(exc,'code',type(exc).__name__)})
            raise
        self.timeline.speech.append({'index':len(self.timeline.speech),'content':content,
                                     'reply':deepcopy(reply),'record_count':len(self.timeline.records)})
        return reply
    def diagnose(self, *, note, diagnosis, **kwargs):
        self.timeline.final={'note':deepcopy(note),'diagnosis':diagnosis}
        if self.timeline.trace:self.timeline.trace.emit('safety_triplet',timeline=self.timeline.snapshot())
        return self.client.diagnose(note=note,diagnosis=diagnosis,**kwargs)


def install(timeline):
    """Install after a selected RAG overlay; restore before restoring that overlay."""
    from examples import hybrid_agent as H
    previous=H.write_record
    def record(client,db,kb,opening,vitals,transcript,contextual_plan=False):
        note,diagnosis=previous(client,db,kb,opening,vitals,transcript,contextual_plan)
        timeline.record(opening,vitals,transcript,note,diagnosis)
        return note,diagnosis
    H.write_record=record
    return previous


def restore(previous):
    from examples import hybrid_agent as H
    H.write_record=previous
