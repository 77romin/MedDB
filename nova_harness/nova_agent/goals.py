"""Encounter-specific decision goals; source checks do not verify clinical meaning."""
import re


class DecisionGoals:
    def __init__(self, state):
        self.state = state
        self.items = {}

    def update(self, updates):
        accepted, rejected = [], []
        sources = {'initial': str(self.state.initial.get('opening', ''))}
        sources.update({e.id: e.response for e in self.state.evidence})
        if not isinstance(updates, list):
            return [], ['goal_updates must be an array']
        for item in updates[:3]:
            if not isinstance(item, dict):
                rejected.append('goal must be an object'); continue
            gid, status = item.get('id'), item.get('status')
            if (not isinstance(gid, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', gid)
                    or not isinstance(status, str) or status not in {'open', 'partial', 'resolved', 'deferred'}
                    or not isinstance(item.get('priority'), str)
                    or item['priority'] not in {'safety', 'decision', 'supporting'}):
                rejected.append('invalid goal identity/status/priority'); continue
            if any(not isinstance(item.get(k), str) or not 1 <= len(item[k].strip()) <= 100
                   for k in ('need', 'scope', 'reason')):
                rejected.append('goal needs bounded need, scope and reason'); continue
            refs = item.get('evidence', [])
            if (not isinstance(refs, list) or len(refs) > 3 or any(
                    not isinstance(ref, dict) or not isinstance(ref.get('id'), str) or ref['id'] not in sources
                    or not isinstance(ref.get('quote'), str) or not ref['quote'].strip()
                    or ref['quote'] not in sources[ref['id']] for ref in refs)):
                rejected.append('goal evidence must quote actual responses or opening'); continue
            if status in {'resolved', 'partial'} and not refs:
                rejected.append('partial/resolved goal needs actual response evidence'); continue
            if status == 'resolved' and any(re.fullmatch(
                    r'\s*(?:모르겠어요|모릅니다|기억이?\s*안\s*나요)[.!。]?\s*', sources[r['id']]) for r in refs):
                rejected.append('explicit unknown cannot resolve a decision goal'); continue
            prior = self.items.get(gid)
            if prior and prior['scope'] != item['scope']:
                rejected.append('scope is immutable; use a new goal for a different time/subject/range'); continue
            if not prior and len(self.items) >= 8:
                rejected.append('at most eight active goals; update an existing goal'); continue
            value = {k: item[k] for k in ('id', 'need', 'scope', 'status', 'priority', 'reason')}
            value['evidence'] = refs
            value['verification'] = 'source_checked_model_interpretation'
            self.items[gid] = value
            accepted.append(value)
        self.state.decision_goals = list(self.items.values())
        return accepted, rejected

    def snapshot(self):
        return {'goals': list(self.items.values()),
                'warning': 'Model-scoped decision needs, not a mandatory checklist or clinically verified completion. '
                           'Resolved source quotes do not establish unasked subjects/times/components.'}
