"""Read a local official OBO file; no network or automatic semantic matching."""
import hashlib
from pathlib import Path

def read_obo(path):
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8')
    version = next((line.split(': ',1)[1] for line in text.splitlines() if line.startswith('data-version: ')), None)
    if not version:
        raise ValueError('OBO data-version missing')
    terms = {}
    for block in text.split('\n[Term]\n')[1:]:
        fields = {}
        for line in block.splitlines():
            key, sep, value = line.partition(': ')
            if sep: fields.setdefault(key, []).append(value)
        if not fields.get('id') or not fields.get('name'): continue
        terms[fields['id'][0]] = dict(id=fields['id'][0], label=fields['name'][0], obsolete=fields.get('is_obsolete') == ['true'], parents=[x.split(' ! ')[0] for x in fields.get('is_a',[])])
    return dict(version=version, sha256=hashlib.sha256(raw).hexdigest(), terms=terms)

def verify_mappings(obo, proposals):
    result = []
    for p in proposals:
        term = obo['terms'].get(p['target'])
        if term is None or term['obsolete'] or term['label'] != p['target_label']:
            raise ValueError('Missing, obsolete or label-mismatched term: '+p['target'])
        if p['relation'] not in {'exact','broad','narrow','related'}:
            raise ValueError('Invalid mapping relation')
        result.append(dict(p, source_version=obo['version'], identifier_verified=True, review_status='draft', reviewer=None))
    return result
