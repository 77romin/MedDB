"""Graph-derived collection coverage. Attempts and model-resolved observations stay distinct."""
from .validation import action_key


class CoveragePlanner:
    def __init__(self, advisor, state):
        self.advisor = advisor
        self.state = state
        self.initial = {}

    def actions(self):
        a = self.advisor
        if not a.complaint:
            return []
        rows = []
        def add(fid, priority, purpose):
            row = a.slots.get(fid) or a.findings.get(fid) or a.exams.get(fid)
            if not row or not a.fits(row) or (fid == 'ex_tanner' and (a.age is None or a.age < 10)):
                return
            kind = 'EXAM' if fid in a.exams else 'SAY'
            text = row.get('action' if kind == 'EXAM' else 'ask')
            if not text or len(text) > 30 or any(r['target'] == 'meddb:'+fid for r in rows):
                return
            rows.append({'type':kind, 'content':text, 'target':'meddb:'+fid,
                         'priority':priority, 'purpose':purpose, 'communication':[]})
        for fid in a.complaint.get('slots', []): add(fid, 1, '주호소 경과')
        for fid in a.complaint.get('ask', []): add(fid, 2, '주호소 구분')
        ranked = a.context(self.state)['hypotheses']
        if ranked and ranked[0]['heuristic_score'] >= 4 and len(ranked[0]['supported']) >= 2:
            disease = a.diseases[ranked[0]['id']]
            count = 0
            for fid in (disease.get('key') or [])+(disease.get('support') or []):
                row = a.findings.get(fid)
                if not row or row.get('kind') == 'sign':
                    continue
                if any(r['target'] == 'meddb:'+fid for r in rows):
                    continue
                add(fid, 2.5, '지지된 가설 구분')
                count += 1
                if count >= 4: break
        for fid in a.complaint.get('exams', []): add(fid, 3, '주호소 표적 진찰')
        for fid in a.graph.get('background', []): add(fid, 4, '기본 병력')
        return sorted(rows, key=lambda r:r['priority'])

    def target_for(self, kind, text):
        key = action_key(kind, text)
        return next((a['target'] for a in self.actions() if action_key(a['type'], a['content']) == key), '')

    def accept_initial(self, items):
        if not isinstance(items, list):
            return
        allowed = {a['target'] for a in self.actions() if a['type'] == 'SAY'}
        opening = str(self.state.initial.get('opening', ''))
        for item in items[:8]:
            if not isinstance(item, dict): continue
            target, quote = item.get('target'), item.get('quote')
            if isinstance(target,str) and target in allowed and isinstance(quote, str) and len(quote.strip()) >= 2 and quote in opening:
                self.initial[target] = quote  # Source verified; semantic mapping is still model-proposed.

    def status(self, action):
        target = action['target']
        facts = [f for f in self.state.facts if f['concept_id'] == target]
        polarities = {f['assertion'] for f in facts if f['assertion'] in {'present','absent'}}
        if len(polarities) > 1:
            return 'conflicting'
        if polarities:
            return 'resolved_model_extracted'
        if target in self.initial:
            return 'initial_model_mapped'
        attempted = any(e.target == target or action_key(e.action, e.question) == action_key(action['type'], action['content'])
                        for e in self.state.evidence)
        if action['type'] == 'EXAM' and attempted:
            return 'exam_result_obtained'
        if attempted or facts:
            return 'attempted_unresolved'
        if action_key(action['type'], action['content']) in self.state.seen:
            return 'rejected_or_attempted'
        return 'unasked'

    def snapshot(self, compact=False):
        actions = self.actions()
        observations = [{**a, 'status':self.status(a), 'initial_quote':self.initial.get(a['target'])} for a in actions]
        if compact:
            observations = [{k:r[k] for k in ('target','status')} for r in observations]
        return {'observations':observations,
                'next_unasked': [a for a in actions if self.status(a) == 'unasked'][:4],
                'warning':'Coverage is collection status, not diagnosis or clinical verification. Unknown/partial answers are unresolved.'}

    def urgent_exit(self, proposal):
        valid = {'initial'} | {e.id for e in self.state.evidence}
        ids = proposal.get('urgency_evidence_ids', [])
        return (proposal.get('urgent_exit') is True and isinstance(ids, list) and bool(ids)
                and all(isinstance(eid, str) and eid in valid for eid in ids)
                and isinstance(proposal.get('urgent_reason'), str) and bool(proposal['urgent_reason'].strip()))

    def choose(self, proposal, remaining, reserve):
        if not isinstance(proposal,dict):
            return proposal, None
        pending = [a for a in self.actions() if self.status(a) == 'unasked']
        if not pending:
            return proposal, None
        urgent = self.urgent_exit(proposal)
        kind = str(proposal.get('type', '')).upper()
        if kind not in {'SAY','EXAM','DONE'}:
            return proposal, None
        tags = proposal.get('communication', [])
        tags = [tags] if isinstance(tags, str) else tags if isinstance(tags, list) else []
        # A valid core choice should not be displaced by the late-turn queue rule.
        if kind in {'SAY','EXAM'} and not tags and (not urgent or kind=='EXAM'):
            core = next((a for a in pending if a['type']==kind and (a['target']==proposal.get('target')
                        or (isinstance(proposal.get('content'),str) and action_key(kind,proposal['content'])==action_key(kind,a['content'])))), None)
            if core:
                canonical = {**proposal,'content':core['content'],'target':core['target']}
                event = None if canonical.get('content')==proposal.get('content') else {
                    'reason':'canonical_target_action','original':proposal,'target':core['target']}
                return canonical,event
        if urgent:
            return proposal, None
        safety = 'safety_net' in tags
        early_explanation = bool({'assessment','plan'}.intersection(tags)) and not safety
        exhausted_frontier = remaining-reserve <= len(pending)+1 and not safety and kind == 'SAY' and not tags
        if kind == 'DONE' or early_explanation or exhausted_frontier:
            return dict(pending[0]), {'reason':'unasked_core_observation', 'original':proposal,
                                     'pending_count':len(pending), 'target':pending[0]['target']}
        return proposal, None
