import json
from dataclasses import dataclass, field


@dataclass
class Evidence:
    id: str
    action: str
    question: str
    response: str
    turn: int
    target: str = ''
    communication: tuple = ()


@dataclass
class PatientState:
    initial: dict
    concepts: dict
    evidence: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    communication: set = field(default_factory=set)
    seen: set = field(default_factory=set)
    turns_used: int = 0

    def add_response(self, action, content, reply, target='', communication=()):
        response = reply.get('content' if action == 'SAY' else 'result', '')
        if not isinstance(response, str):
            response = json.dumps(response, ensure_ascii=False)
        turn = reply.get('turn')
        if not isinstance(turn, int):
            turn = self.turns_used+1
        self.turns_used = turn
        allowed = {'empathy', 'assessment', 'plan', 'follow_up', 'safety_net', 'concern',
                   'answer', 'teach_back', 'concern_question'}
        tags = [communication] if isinstance(communication, str) else communication
        tags = tags if isinstance(tags, (list, tuple, set)) else ()
        tags = tuple(t for t in tags if isinstance(t, str) and t in allowed) if action == 'SAY' else ()
        item = Evidence(f'e{len(self.evidence)+1}', action, content, response, turn, target, tags)
        self.evidence.append(item)
        self.communication.update(tags)
        return item

    def delivered_explanations(self):
        """Actual successful SAYs with declared purpose; tags do not prove clinical adequacy."""
        kinds = {'assessment', 'plan', 'follow_up', 'safety_net', 'concern', 'answer'}
        return [e for e in self.evidence if e.action == 'SAY' and kinds.intersection(e.communication)]

    def accept_facts(self, proposed):
        accepted, rejected = [], []
        sources = {e.id: e for e in self.evidence}
        if not isinstance(proposed, list):
            return [], ['facts must be an array']
        for p in proposed:
            if not isinstance(p, dict):
                rejected.append('fact must be an object'); continue
            source = sources.get(p.get('evidence_id'))
            quote, concept, assertion = p.get('quote'), p.get('concept_id'), p.get('assertion')
            if (source is None or concept not in self.concepts
                    or not isinstance(quote, str) or not quote.strip() or quote not in source.response
                    or assertion not in {'present', 'absent', 'uncertain', 'unknown'}):
                rejected.append('fact lacks an exact patient-response quote, known concept, or assertion'); continue
            kind = self.concepts[concept].get('kind')
            if (source.action == 'EXAM') != (kind == 'sign'):
                rejected.append('physical signs require EXAM evidence; history/symptoms require patient answers'); continue
            if source.response.strip() in {'한 번에 하나씩 물어봐 주세요.', '한 번에 하나씩 물어봐 주세요'}:
                rejected.append('patient refused a compound question; no clinical fact'); continue
            subject = p.get('subject', 'patient')
            if subject not in {'patient', 'family', 'other', 'unknown'}:
                rejected.append('invalid fact subject'); continue
            candidate = {'concept_id': concept, 'quote': quote, 'assertion': assertion,
                         'evidence_id': source.id, 'subject': subject,
                         'temporality': str(p.get('temporality', 'unknown')),
                         'status': 'model_extracted_quote_verified'}
            if any(all(f.get(k) == candidate[k] for k in candidate) for f in self.facts):
                continue
            candidate['id'] = f'f{len(self.facts)+1}'
            self.facts.append(candidate); accepted.append(candidate)
        return accepted, rejected

    def snapshot(self):
        covered = {f['concept_id'] for f in self.facts if f['assertion'] in {'present', 'absent'}}
        # Semantic negation/temporality is model-extracted, not established by substring validation.
        return {'initial': self.initial, 'facts': self.facts,
                'evidence': [vars(e) for e in self.evidence],
                'unconfirmed_slots': [c for c in self.concepts if c not in covered],
                'communication_claimed_sent': sorted(self.communication), 'errors': self.errors[-8:]}

    def prompt_snapshot(self):
        """Keep every original response, but avoid repeating its quote again in the fact list."""
        value = self.snapshot()
        value['facts'] = [{k:v for k,v in f.items() if k not in {'quote','status'}} for f in self.facts]
        return value
