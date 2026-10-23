"""Order existing eligible coverage candidates by unfilled history domains.

An experimental coverage heuristic, not information gain, diagnosis probability,
or an active differential convergence engine. It neither adds candidate actions
nor changes facts, source records, diagnostic ranking or termination budgets.
Install after response_state; restore in reverse order.
"""
from collections import Counter

SAFETY = frozenset({'meds','allergy','pregnancy','breastfeeding','med_name',
                    'med_schedule','med_duration','supplements'})
CORE_TIME = frozenset({'onset','course'})


def domain(care, target, kind='SAY'):
    if kind == 'EXAM' or target in care.db.exams:
        return 'exam'
    if target in SAFETY:
        return 'treatment_safety'
    if target in care.extra:
        return care.extra[target][1]
    if target in ('family','parent_height'):
        return 'fh'
    if target in ('pmh','chronic_illness','surgery'):
        return 'pmh'
    if any(fid == target for _,fid in care.db.background):
        return 'background'
    return 'hpi'


def order(care, kb, actions):
    # Received only drives distribution of question topics, not truth/normality.
    counts = Counter(domain(care,t) for t,row in care.response_slots.items()
                     if row['status']=='received')
    successful_history = sum(counts.values())
    exam_count = len(kb.exams_done)
    def rank(pair):
        index,a = pair
        target=a.get('target');priority=a.get('priority',99)
        if priority <= 0:
            return (0, priority, 0, index)  # Existing conflict/red-flag precedence.
        if target in CORE_TIME:
            return (1, priority, 0, index)
        if target in SAFETY:
            return (2, priority, 0, index)
        d=domain(care,target,a['type'])
        if a['type']=='EXAM':
            # Delay routine exams until some history exists; avoid leaving every
            # existing relevant exam behind a long symptom queue.
            return (3 if successful_history>=8 and exam_count==0 else 4,
                    0 if exam_count==0 else exam_count, priority, index)
        return (3, counts[d], priority, index)
    indexed=sorted(enumerate(actions),key=rank)
    return [a for _,a in indexed],dict(counts)


def install(events):
    from meddb import coverage
    original=coverage.CareCoverage
    class OrderedCoverage(original):
        def needed(self,kb):
            actions=super().needed(kb)
            if not actions:return actions
            ranked,counts=order(self,kb,actions)
            events.append({'event':'coverage_order','original_first':actions[0].get('target'),
                           'selected':ranked[0].get('target'),
                           'changed':ranked[0] is not actions[0],
                           'received_by_domain':counts,
                           'evidence_turns':sorted({r['turn'] for r in self.response_slots.values()}),
                           'candidates':[{'target':a.get('target'),'kind':a['type'],
                                          'priority':a.get('priority')} for a in actions],
                           'ordered_targets':[a.get('target') for a in ranked]})
            return ranked
    coverage.CareCoverage=OrderedCoverage
    return original


def restore(original):
    from meddb import coverage
    coverage.CareCoverage=original
