"""Evidence retrieval scores, deliberately not calibrated disease probabilities."""
from collections import defaultdict
import math


def relation_polarity(assertion):
    if assertion.get('polarity') in {'associated','excluded'}:
        return assertion['polarity']
    return 'excluded' if str(assertion.get('frequency_label','')).strip().upper()=='EXCLUDED' else 'associated'


def rank_candidates(kb, observations, include_draft, limit, patient, category):
    patient = {} if patient is None else patient
    if not isinstance(patient, dict) or set(patient) - {'age', 'sex', 'puberty_assessment'}:
        raise ValueError('Invalid patient fields')
    if patient.get('puberty_assessment') not in {None,'unknown','appropriate','not_age_appropriate'}:
        raise ValueError('Invalid puberty assessment context')
    age, sex = patient.get('age'), patient.get('sex')
    if age is not None and (type(age) not in {int, float} or not math.isfinite(age) or not 0 <= age <= 130):
        raise ValueError('Age must be between 0 and 130')
    if sex is not None and sex not in {'female', 'male', 'unknown'}:
        raise ValueError('Invalid sex')
    diseases = [n for n in kb.nodes.values() if n['kind'] == 'Disease']
    categories = sorted({n.get('category') for n in diseases if n.get('category')})
    if category is not None and category not in categories:
        raise ValueError('Unknown category')
    grouped = defaultdict(lambda: defaultdict(list))
    prevalence = defaultdict(set)
    for a in kb.assertions(include_draft):
        if a['predicate'] == 'has_phenotype':
            grouped[a['subject']][a['object']].append(a)
            if relation_polarity(a) == 'associated':
                prevalence[a['object']].add(a['subject'])
    weights = {f: 1 + math.log((1 + len(diseases))/(1 + len(ds))) for f, ds in prevalence.items()}
    context_ignored=[]
    if patient.get('puberty_assessment')=='not_age_appropriate':
        context_ignored=[f for f in observations if kb.nodes[f]['label_en']=='Delayed puberty' and observations[f]!='unknown']
    known = {f: s for f, s in observations.items() if s != 'unknown' and f not in context_ignored}
    # Normalize against the same patient evidence for every candidate, not each disease's record size.
    denominator = sum(weights.get(f, 1) for f in known) or 1
    candidates, filtered = [], []
    for disease in diseases:
        if category and disease.get('category') != category:
            continue
        constraints = disease.get('clinical_constraints', {})
        reasons = []
        # Only explicitly reviewed eligibility constraints can exclude a candidate.
        if constraints.get('review_status') == 'reviewed' and constraints.get('reviewer') and constraints.get('source_id') in kb.sources and constraints.get('locator'):
            if age is not None and ((constraints.get('min_age') is not None and age < constraints['min_age']) or (constraints.get('max_age') is not None and age > constraints['max_age'])):
                reasons.append('outside_reviewed_age_range')
            if sex in {'female', 'male'} and constraints.get('sex') in {'female', 'male'} and sex != constraints['sex']:
                reasons.append('outside_reviewed_sex_constraint')
        if reasons:
            filtered.append({'disease_id': disease['id'], 'reasons': reasons, 'constraint': constraints})
            continue
        matched, conflicts, evidence, explanations, uncertain = [], [], [], [], []
        support = penalty = 0.0
        for finding, rows in grouped[disease['id']].items():
            state = known.get(finding)
            if state is None:
                continue
            polarities = {relation_polarity(a) == 'excluded' for a in rows}
            if len(polarities) > 1:
                uncertain.append(finding)
                evidence.extend(rows)
                continue
            excluded = True in polarities
            supports = (excluded and state == 'absent') or (not excluded and state == 'present')
            weight = weights.get(finding, 1)
            # Missing an optional phenotype is weaker counter-evidence than an explicit exclusion.
            factor = 1.0 if supports or excluded else 0.25
            contribution = weight * factor
            if supports:
                matched.append(finding)
                support += contribution
            else:
                conflicts.append(finding)
                penalty += contribution
            evidence.extend(rows)
            explanations.append({'finding': finding, 'observed': state, 'relation_polarity': 'excluded' if excluded else 'associated', 'contribution': round(contribution if supports else -contribution, 4), 'contexts': [{'assertion_id': a['id'], 'context': a['context'], 'source_id': a['source_id'], 'locator': a['locator']} for a in rows]})
        if not matched:
            continue
        next_findings = sorted((f for f, rows in grouped[disease['id']].items() if f not in known and all(relation_polarity(a)=='associated' for a in rows)), key=lambda f: (-weights.get(f, 1), f))[:5]
        candidates.append({'disease': disease, 'matched': sorted(matched), 'conflicts': sorted(conflicts), 'uncertain': sorted(uncertain), 'evidence': evidence, 'score': round((support-penalty)/denominator, 6), 'support_score': round(support, 4), 'conflict_score': round(penalty, 4), 'explanations': explanations, 'next_findings': [{'id': f, 'label': kb.nodes[f]['label_ko']} for f in next_findings]})
    candidates.sort(key=lambda c: (-c['score'], -len(c['matched']), len(c['conflicts']), c['disease']['id']))
    # Rank ties are explicit: arbitrary ID order does not imply clinical preference.
    last, rank = None, 0
    for i, c in enumerate(candidates, 1):
        key = (c['score'], len(c['matched']), len(c['conflicts']))
        if key != last:
            rank, last = i, key
        c['rank'] = rank
    total = len(candidates)
    candidates = candidates[:limit]
    active_constraints = any(n.get('clinical_constraints', {}).get('review_status') == 'reviewed' and n.get('clinical_constraints', {}).get('reviewer') and n.get('clinical_constraints', {}).get('source_id') in kb.sources and n.get('clinical_constraints', {}).get('locator') for n in diseases)
    warnings = []
    if any(patient.get(field) is not None and patient.get(field)!='unknown' for field in ('age','sex')) and not active_constraints:
        warnings.append('No reviewed age/sex eligibility rules in this snapshot; patient conditions did not filter diseases.')
    if include_draft:
        warnings.append('Draft medical relationships included.')
    return {'version': kb.version, 'sha256': kb.sha256, 'total_candidates': total, 'interpretation': 'IDF-weighted evidence score; not diagnostic probability. Optional phenotype absence is weak counter-evidence. EXCLUDED is negative evidence.', 'score_method': 'phenotype-idf-v2-context', 'include_draft': include_draft, 'patient': patient, 'category': category, 'context_ignored':context_ignored, 'warnings': warnings, 'filtered': filtered, 'candidates': candidates, 'sources': [kb.sources[s] for s in sorted({a['source_id'] for c in candidates for a in c['evidence']})]}
