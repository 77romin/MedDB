import json
import re
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
    compact_context: bool = True

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
            if assertion in {'present','absent'} and re.fullmatch(r'\s*(?:모르겠어요|모릅니다|기억이?\s*안\s*나요)[.!。]?\s*', source.response):
                rejected.append('explicit unknown answer cannot establish presence or absence'); continue
            if p.get('subject','patient') == 'patient' and re.match(r'\s*(?:(?:제|저희|우리)\s*)?(?:어머니|아버지|엄마|아빠|형|누나|언니|동생|남편|아내|아들|딸)(?:은|는|이|가)\s',quote):
                rejected.append('quote starts with a family subject; do not assign it to the patient'); continue
            if assertion == 'absent' and source.action == 'SAY':
                if not re.search(r'아니|아닙|없|않|못|부인|(?:^|\s)안\s|안(?:먹|마시|피우|해|드|하)', source.response):
                    rejected.append('absence needs explicit negative response; positive answer cannot deny another symptom'); continue
                if re.search(r'(?:평소|이전|전보다|더).*(?:심하|나쁘|악화).*(?:않|아니)', source.response):
                    rejected.append('comparative non-worsening does not establish absolute absence'); continue
            expected_exam = self.concepts[concept].get('exam_target')
            if assertion == 'absent' and source.action == 'EXAM' and expected_exam and source.target != expected_exam:
                rejected.append('normality in another or unidentified exam cannot deny this sign'); continue
            if source.response.strip() in {'한 번에 하나씩 물어봐 주세요.', '한 번에 하나씩 물어봐 주세요'}:
                rejected.append('patient refused a compound question; no clinical fact'); continue
            subject = p.get('subject', 'patient')
            if subject not in {'patient', 'family', 'other', 'unknown'}:
                rejected.append('invalid fact subject'); continue
            candidate = {'concept_id': concept, 'quote': quote, 'assertion': assertion,
                         'evidence_id': source.id, 'subject': subject,
                         'temporality': str(p.get('temporality', 'unknown')),
                         'status': 'model_extracted_quote_verified'}
            # Preserve the observed strings; never compute a daily total, convert
            # units, or borrow a time/value from the doctor's question.
            attributes = {'drug_name','strength','dose_count','frequency','last_dose',
                          'duration','severity','measurement','functional_effect'}
            attribute = p.get('attribute')
            if attribute is not None:
                if not isinstance(attribute,str) or attribute not in attributes or not isinstance(p.get('value'),str) or not p['value'].strip():
                    rejected.append('invalid structured attribute or missing value'); continue
                fields = {k:p[k] for k in ('value','unit','time_anchor') if k in p}
                if any(not isinstance(v,str) or not v.strip() or len(v)>100 or v not in quote for v in fields.values()):
                    rejected.append('structured value/unit/time must occur in the same exact response quote'); continue
                value_unit = re.escape(fields['value'])+r'\s*'+re.escape(fields.get('unit',''))
                if assertion in {'present','absent'} and re.search(value_unit+r'(?:인지|였는지|었는지).{0,20}(?:모르|기억)',quote):
                    rejected.append('explicit uncertainty attached to the observed value cannot establish it'); continue
                uncertainty_cues = {
                    'strength':r'함량|밀리그램|mg', 'dose_count':r'몇\s*알|개수|복용량|용량',
                    'frequency':r'횟수|몇\s*번', 'duration':r'기간|며칠|언제부터',
                    'last_dose':r'마지막|언제|시점', 'measurement':r'수치|측정값',
                }
                cues = uncertainty_cues.get(attribute)
                if assertion in {'present','absent'} and cues and re.search(r'(?:'+cues+r').{0,18}(?:모르|몰라|기억.{0,4}안)',source.response):
                    rejected.append('the response explicitly leaves this attribute unknown'); continue
                if assertion in {'present','absent'} and re.search(value_unit+r'\s*(?:보다|이상|이하|미만|초과|에서|~|정도|쯤)',source.response):
                    rejected.append('a comparative/range/approximate value is not an exact measurement; retain the full response as uncertain'); continue
                candidate.update(attribute=attribute, **fields)
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

    def prompt_snapshot(self, relevant_concepts=None):
        """Keep every original response, but avoid repeating its quote again in the fact list."""
        value = self.snapshot()
        value['facts'] = [{k:v for k,v in f.items() if k not in {'quote','status'}} for f in self.facts]
        if self.compact_context:
            if relevant_concepts is None:
                value.pop('unconfirmed_slots',None)
            else:
                relevant = set(relevant_concepts)
                value['unconfirmed_slots'] = [cid for cid in value['unconfirmed_slots'] if cid in relevant]
        return value
