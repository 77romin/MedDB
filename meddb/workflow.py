"""Conservative normalization and evidence-bearing development tools."""
import hashlib
import json
import math
from pathlib import Path
import re
from .ranking import relation_polarity

RESOURCES = Path(__file__).resolve().parents[1] / 'data' / 'agent'


def resource(name):
    raw = (RESOURCES / name).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def resolve(kb, entry):
    if entry.get('id') in kb.nodes:
        return [entry['id']]
    return [n['id'] for n in kb.nodes.values() if n['kind']=='Finding' and n['label_en'].casefold()==entry.get('english','').casefold()]


def profile_kb(kb, profile):
    from copy import copy
    profiles, digest = resource('profiles.json')
    if profile not in profiles['profiles']:
        raise ValueError('Unknown knowledge profile')
    policy = profiles['profiles'][profile]
    view = copy(kb)
    assertions = kb.assertions(policy['include_draft'])
    if policy.get('source_prefix'):
        assertions = [a for a in assertions if a['source_id'].startswith(policy['source_prefix'])]
    view.data = dict(kb.data, assertions=assertions)
    metadata = {'name': profile, 'policy_sha256': digest, **policy, 'assertions': len(assertions), 'reviewed': sum(a['review_status']=='reviewed' for a in assertions), 'draft': sum(a['review_status']=='draft' for a in assertions)}
    return view, metadata


def normalize(kb, text):
    if not isinstance(text, str) or not text.strip() or len(text)>10000:
        raise ValueError('Text must contain 1-10000 characters')
    dictionary, digest = resource('phrases.json')
    mentions, unmatched = [], []
    # Each statement has its own negation scope. Multiple mentions with negation are ambiguous.
    for clause in filter(None, (s.strip() for s in re.split(r'[\n;。.!]+',text))):
        hits, occupied = [], []
        phrases = sorted(((phrase, entry) for entry in dictionary['entries'] for phrase in entry['phrases']),key=lambda x:-len(x[0]))
        for phrase, entry in phrases:
            start = clause.casefold().find(phrase.casefold())
            if start < 0 or any(start < end and start+len(phrase)>begin for begin,end in occupied):
                continue
            ids = resolve(kb, entry)
            if not ids:
                continue
            occupied.append((start,start+len(phrase)))
            hits.append((phrase,entry,ids))
        if not hits:
            unmatched.append(clause)
            continue
        negation_text = re.sub(r'잠(?:을|이)?\s*(?:안\s*와|(?:잘\s*)?못\s*자)', '불면', clause)
        negative = bool(re.search(r'없|않|아니|안\s|부인|못',negation_text))
        uncertain = bool(re.search(r'모르|미확인|확인.*못|물어보|\?|과거|예전|이전에|전에|가족|어머니|아버지|엄마|아빠|수년|복용|없.*않|않.*없',clause))
        durations = re.findall(r'\d+\s*(?:년|개월|달|주|일|시간)',clause)
        for phrase,entry,ids in hits:
            ambiguous = uncertain or len(ids)!=1 or (negative and len(hits)>1)
            state = 'unknown' if ambiguous else ('absent' if negative else 'present')
            mentions.append({'phrase':phrase,'statement':clause,'candidate_ids':ids,'labels':[kb.nodes[i]['label_ko'] for i in ids],'proposed_state':state,'needs_confirmation':True,'reason':'ambiguous_scope_or_context' if ambiguous else 'dictionary_match','duration_mentions':durations,'mapping_status':'draft'})
    states = {}
    for m in mentions:
        for f in m['candidate_ids']:
            states.setdefault(f,set()).add(m['proposed_state'])
    conflicts = [f for f,s in states.items() if 'present' in s and 'absent' in s]
    for m in mentions:
        if any(f in conflicts for f in m['candidate_ids']):
            m['proposed_state']='unknown'
            m['reason']='contradictory_statements'
    return {'version':kb.version,'dictionary_version':dictionary['version'],'dictionary_sha256':digest,'mentions':mentions,'unmatched':unmatched,'conflicts':conflicts,'interpretation':'Proposed mappings only. Confirm observation state before ranking; durations and medication context are not diagnostic rules.'}


def suggest(kb, observations, profile='reviewed', patient=None, category=None, limit=5):
    if type(limit) is not int or not 1<=limit<=20:
        raise ValueError('Action limit must be 1-20')
    view, policy = profile_kb(kb,profile)
    ranked = view.rank(observations,policy['include_draft'],limit=10,patient=patient,category=category)
    candidates = ranked['candidates']
    actions, action_digest = resource('actions.json')
    templates = {}
    for entry in actions['entries']:
        for finding in resolve(kb,entry):
            templates[finding]=entry
    by_finding = {}
    selected = {c['disease']['id'] for c in candidates}
    for a in view.assertions(policy['include_draft']):
        if a['predicate']!='has_phenotype' or a['subject'] not in selected or observations.get(a['object'],'unknown')!='unknown':
            continue
        slot = by_finding.setdefault(a['object'],{})
        slot.setdefault(a['subject'],[]).append(a)
    recommendations = []
    for finding, disease_rows in by_finding.items():
        polarities = {}
        for d,rows in disease_rows.items():
            values = {relation_polarity(a) for a in rows}
            if len(values)==1:
                polarities[d]=next(iter(values))
        pos = sorted(d for d,p in polarities.items() if p=='associated')
        neg = sorted(d for d,p in polarities.items() if p=='excluded')
        if not pos and not neg:
            continue
        # Measures structural candidate separation, not expected clinical information gain.
        p = len(pos)/max(1,len(candidates))
        separation = -sum(x*math.log2(x) for x in (p,1-p) if x>0)
        if neg and pos:
            separation += 1
        entry = templates.get(finding)
        if kb.nodes[finding]['label_en']=='Delayed puberty' and (patient or {}).get('puberty_assessment')!='appropriate':
            entry = None
        if entry and not policy['include_draft'] and entry['review_status']!='reviewed':
            entry = None
        relations = [a for d,rows in disease_rows.items() if d in polarities for a in rows]
        proposal = {'finding':finding,'label':kb.nodes[finding]['label_ko'],'separation_score':round(separation,4),'associated_candidates':pos,'excluded_candidates':neg,'unrecorded_candidates':sorted(selected-set(polarities)),'evidence':[{'assertion_id':a['id'],'source_id':a['source_id'],'locator':a['locator'],'context':a['context'],'review_status':a['review_status'],'polarity':relation_polarity(a)} for a in relations], 'action':entry['action'] if entry else None,'content':entry['content'] if entry else None,'template_status':entry['review_status'] if entry else 'missing','template_source':entry.get('source') if entry else None,'requires_clinical_review':True}
        recommendations.append(proposal)
    recommendations.sort(key=lambda a:(a['action'] is None,-a['separation_score'],a['finding']))
    if (patient or {}).get('puberty_assessment')=='not_age_appropriate':
        recommendations=[r for r in recommendations if kb.nodes[r['finding']]['label_en']!='Delayed puberty']
    checklists, checklist_digest = resource('checklists.json')
    activated = [entry for entry in checklists['entries'] if policy['include_draft'] and all(observations.get(f)=='present' for f in entry['trigger_all'])]
    return {'version':kb.version,'sha256':kb.sha256,'policy':policy,'action_dictionary_sha256':action_digest,'checklist_sha256':checklist_digest,'ranking':ranked,'recommendations':recommendations[:limit],'checklists':activated,'interpretation':'Advisory development proposals. An unrecorded phenotype is not an absent phenotype. EXAM recognition is not guaranteed by the competition server.'}
