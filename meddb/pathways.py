"""Context and history aids kept separate from phenotype-ranking evidence."""
import unicodedata
from .workflow import resource


def recommend(kb, observations, history=None, include_draft=False):
    # Validate inputs through the existing KB interface without enabling draft ranking.
    kb.rank(observations)
    history={} if history is None else history
    if not isinstance(history,dict):raise ValueError('History must be an object')
    catalog,digest=resource('clinical-pathways.json')
    allowed={r['id'] for p in catalog['entries'] for r in p['requirements']}
    if set(history)-allowed:raise ValueError('Unknown history requirement')
    for key,item in history.items():
        if not isinstance(item,dict) or item.get('status') not in {'unknown','confirmed','not_applicable'}:raise ValueError('Invalid history state')
        if item['status']!='unknown' and (not isinstance(item.get('value'),str) or not item['value'].strip() or not item.get('evidence_id')):raise ValueError('History completion needs value and evidence ID')
    result=[]
    if include_draft:
        for pathway in catalog['entries']:
            if not any(observations.get(f)=='present' for f in pathway['trigger_any']):continue
            pending=[]
            for requirement in sorted(pathway['requirements'],key=lambda r:(r['priority'],r['id'])):
                if history.get(requirement['id'],{}).get('status') in {'confirmed','not_applicable'}:continue
                row=dict(requirement,review_status='draft',sources=pathway['sources'])
                for question in row['questions']:
                    if not 0<len(unicodedata.normalize('NFC',question))<=30:raise ValueError('Invalid pathway question length')
                if row.get('exam') and len(unicodedata.normalize('NFC',row['exam']))>30:raise ValueError('Invalid exam length')
                pending.append(row)
            result.append({'id':pathway['id'],'title':pathway['title'],'pending':pending,'review_status':'draft'})
    return {'version':catalog['version'],'sha256':digest,'pathways':result,'interpretation':'History/plans are not phenotype observations. A plan is not an performed test or result.'}
