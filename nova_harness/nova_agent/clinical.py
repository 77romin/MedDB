"""Compact MedDB clinical graph adapter. Scores are heuristic, never probabilities."""
import re
from .validation import action_key


def norm(text):
    return re.sub(r'[\s\W_]+', '', text.casefold())


def demographics(opening):
    # Earliest stated age belongs to patient in NOVA openings; uncertain formats stay unknown.
    matches = [(m.start(), int(m[1])) for m in re.finditer(r'(\d{1,3})\s*(?:세|살)', opening)]
    tens = {'열':10,'스물':20,'스무':20,'서른':30,'마흔':40,'쉰':50,'예순':60,'일흔':70,'여든':80,'아흔':90}
    ones = {'한':1,'두':2,'세':3,'네':4,'다섯':5,'여섯':6,'일곱':7,'여덟':8,'아홉':9}
    pattern = r'(?<![가-힣])(열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔)?\s*(한|두|세|네|다섯|여섯|일곱|여덟|아홉)?\s*살'
    for m in re.finditer(pattern, opening):
        age = tens.get(m[1], 0)+ones.get(m[2], 0)
        if age: matches.append((m.start(), age))
    age = min(matches)[1] if matches else None
    sex = re.search('남자|남성|남아|여자|여성|여아', opening)
    return age, ('M' if sex[0].startswith('남') else 'F') if sex else None


class ClinicalAdvisor:
    def __init__(self, graph, opening):
        self.graph = graph
        self.age, self.sex = demographics(opening)
        self.findings = {r['id']:r for r in graph['findings']}
        self.slots = {r['id']:r for r in graph['slots']}
        self.exams = {r['id']:r for r in graph['exams']}
        self.diseases = {r['id']:r for r in graph['diseases']}
        text = norm(opening)
        hits = [(max([len(norm(a)) for a in c.get('alias', []) if norm(a) in text]+[0]), c) for c in graph['complaints']]
        score, self.complaint = max(hits, key=lambda x:x[0]) if hits else (0, None)
        if not score: self.complaint = None

    def concepts(self):
        mapping = {'S.가족력':'fh','S.사회력':'sh','S.약물':'pmh','S.알레르기':'pmh','S.과거력':'pmh','S.현병력':'hpi'}
        result = []
        for category, rows in [('finding',self.findings),('slot',self.slots)]:
            for key, row in rows.items():
                field = 'exam' if row.get('kind') == 'sign' else mapping.get(row.get('soap'), 'ros' if row.get('kind') == 'symptom' else 'hpi')
                result.append({'id': 'meddb:'+key, 'label': row['ko'], 'field': field, 'kind': row.get('kind',category),
                               'exam_target':'meddb:'+row['exam'] if row.get('exam') else None, 'source':'MedDB team draft'})
        return result

    def fits(self, row):
        ages = row.get('age') or [None,None]
        return not ((self.sex and row.get('sex') and row['sex']!=self.sex)
                    or (self.age is not None and (ages[0] is not None and self.age<ages[0] or ages[1] is not None and self.age>ages[1])))

    def context(self, state):
        present, absent = set(), set()
        for f in state.facts:
            if not f['concept_id'].startswith('meddb:'): continue
            if f.get('subject') == 'family' and state.concepts.get(f['concept_id'], {}).get('field') != 'fh': continue
            fid = f['concept_id'][6:]
            if f['assertion']=='present': present.add(fid)
            if f['assertion']=='absent': absent.add(fid)
        conflicts = present & absent
        present -= conflicts; absent -= conflicts
        ranked = []
        for did in self.complaint.get('diseases', []) if self.complaint else []:
            d = self.diseases.get(did)
            if not d or not self.fits(d): continue
            key, support, against = (set(d.get(k) or []) for k in ('key','support','against'))
            score = 3*len(key & present)+len(support & present)-2*len(against & present)-len(key & absent)
            ranked.append({'id':did,'label':d['ko'],'heuristic_score':score,
                           'supported':sorted((key|support)&present),'opposed':sorted((key&absent)|(against&present)),
                           'missing':sorted(key-present-absent)})
        ranked.sort(key=lambda d:-d['heuristic_score'])
        candidates = []
        def add(target, priority, purpose):
            row = self.slots.get(target) or self.findings.get(target) or self.exams.get(target)
            if not row or not self.fits(row): return
            if target=='ex_tanner' and (self.age is None or self.age<10): return
            if target in present|absent: return
            kind = 'EXAM' if target in self.exams else 'SAY'
            text = row.get('action') if kind=='EXAM' else row.get('ask')
            if not text or len(text)>30 or action_key(kind,text) in state.seen: return
            if any(getattr(e,'target','')=='meddb:'+target for e in state.evidence): return
            if any(a['target']=='meddb:'+target for a in candidates): return
            candidates.append({'type':kind,'content':text,'target':'meddb:'+target,'priority':priority,'purpose':purpose})
        if self.complaint:
            for target in self.complaint.get('slots',[]): add(target,1,'현병력')
            for target in self.complaint.get('ask',[]): add(target,2,'주호소 구분 정보')
            for d in ranked[:3]:
                for target in d['missing'][:3]: add(target,3,'감별 구분: '+d['label'])
            for target in self.complaint.get('exams',[]): add(target,4,'주호소 표적 진찰')
        for target in self.graph.get('background',[]): add(target,5,'기본 병력')
        candidates.sort(key=lambda a:a['priority'])
        # Prompt only the decision frontier. Full graph stays local; no clinical evidence is removed.
        ranked = [{**d,'missing':d['missing'][:3],'supported':d['supported'][:4],'opposed':d['opposed'][:3]} for d in ranked[:3]]
        # Do not hide all objective exams behind the history queue.
        frontier = [a for a in candidates if a['type']=='SAY'][:6]+[a for a in candidates if a['type']=='EXAM'][:2]
        for action in candidates:
            if len(frontier)>=8: break
            if action not in frontier:frontier.append(action)
        relevant = {a['target'] for a in frontier}
        for d in ranked: relevant.update('meddb:'+f for f in d['supported']+d['missing']+d['opposed'])
        return {'review':self.graph['review'],'complaint':self.complaint['id'] if self.complaint else None,
                'age':self.age,'sex':self.sex,'hypotheses':ranked,'actions':frontier,
                'conflicts':sorted(conflicts),'relevant_concepts':sorted(relevant),
                'warning':'Draft relations and uncalibrated heuristic ranks; not diagnoses or confirmed absences. Attempted questions do not mean resolved findings.'}
