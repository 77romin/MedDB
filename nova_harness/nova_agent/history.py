"""Extractive SOAP routing: every retained patient value is an actual whole response."""
import re
from collections import defaultdict

FIELDS = {'hpi', 'pmh', 'fh', 'sh', 'ros'}
FAMILY = re.compile(r'가족|부모|어머니|아버지|엄마|아빠|남편|아내|자녀|형제|자매|할머니|할아버지')


def history_routes(state, proposed):
    sources = {e.id: e for e in state.evidence if e.action == 'SAY'}
    claims = defaultdict(set)
    routes = proposed.get('history_routes', {})
    if isinstance(routes, dict):
        for field, ids in routes.items():
            if field not in FIELDS or not isinstance(ids, list):
                continue
            for eid in ids[:50]:
                if not isinstance(eid, str) or eid not in sources:
                    continue
                e = sources[eid]
                if 'teach_back' in e.communication:
                    continue
                if field == 'fh' and not FAMILY.search(e.question+' '+e.response):
                    continue  # Family routing needs at least an explicit family context.
                claims[eid].add(field)
    # An ambiguous model route is not silently resolved by dictionary order.
    chosen = {eid: next(iter(fields)) for eid, fields in claims.items() if len(fields) == 1}
    fallback = defaultdict(set)
    for fact in state.facts:
        eid = fact.get('evidence_id')
        field = state.concepts.get(fact.get('concept_id'), {}).get('field')
        if eid not in sources or field not in FIELDS:
            continue
        if fact.get('subject') == 'family':
            field = 'fh'
        fallback[eid].add(field)
    for eid, fields in fallback.items():
        if eid not in chosen:
            chosen[eid] = next(iter(fields)) if len(fields) == 1 else 'hpi'
    return chosen


def render_history(state, proposed):
    fields = {field: [] for field in FIELDS}
    routes = history_routes(state, proposed)
    explanations = {e.id for e in state.delivered_explanations()}
    for e in state.evidence:
        if e.action != 'SAY' or 'teach_back' in e.communication:
            continue
        field = routes.get(e.id, 'hpi')
        if e.id in explanations and e.id not in routes:
            # Retain nontrivial new answers even if the model failed to classify them.
            if e.response.strip(' .!。') in {'네', '예', '알겠습니다', '네, 알겠습니다', '감사합니다'}:
                continue
            fields[field].append(f'설명 중 추가 응답: {e.response} [{e.id}, 턴 {e.turn}]')
        else:
            fields[field].append(f'{e.question} → {e.response} [{e.id}, 턴 {e.turn}]')
    return {field: '\n'.join(lines) for field, lines in fields.items()}
