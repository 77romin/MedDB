"""Export reified assertions, never turn draft claims into asserted clinical triples."""
import json
from urllib.parse import quote

BASE = 'https://nova.example/ontology/'
def iri(value):
    return '<' + BASE + quote(value, safe='') + '>'
def literal(value):
    return json.dumps(str(value), ensure_ascii=False)
def export(kb, include_draft=False):
    lines = ['@prefix nova: <'+BASE+'> .', '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .', '']
    for n in kb.nodes.values():
        lines.append(f'{iri(n["id"])} a nova:{n["kind"]}, nova:Concept ; rdfs:label {literal(n["label_ko"])}@ko, {literal(n["label_en"])}@en .')
    for n in kb.nodes.values():
        for i, m in enumerate(n['mappings']):
            if m.get('review_status') != 'reviewed' and not (include_draft and m.get('review_status') == 'draft'):
                continue
            mid = iri(n['id'] + ':mapping:' + str(i))
            target = '<http://purl.obolibrary.org/obo/' + m['target'].replace(':', '_') + '>'
            lines.append(iri(n['id'])+' nova:mapping '+mid+' .')
            props = ['a nova:Mapping', 'nova:subject '+iri(n['id']), 'nova:target '+target, 'nova:mappingRelation '+literal(m['relation']), 'nova:source '+iri(m['source_id']), 'nova:reviewStatus '+literal(m.get('review_status','draft')), 'nova:sourceVersion '+literal(m['source_version']), 'nova:targetLabel '+literal(m['target_label'])]
            if m.get('reviewer'): props.append('nova:reviewer '+literal(m['reviewer']))
            lines.append(mid+' '+' ; '.join(props)+' .')
    for s in kb.sources.values():
        lines.append(f'{iri(s["id"])} a nova:Source ; rdfs:label {literal(s["title"])} ; nova:url {literal(s["url"])} ; nova:sourceVersion {literal(s["version"])} .')
    for a in kb.assertions(include_draft):
        props = ['a nova:Assertion', 'nova:subject '+iri(a['subject']), 'nova:predicate nova:'+a['predicate'], 'nova:object '+iri(a['object']), 'nova:source '+iri(a['source_id']), 'nova:locator '+literal(a['locator']), 'nova:context '+literal(a['context']), 'nova:reviewStatus '+literal(a['review_status']), 'nova:extractionMethod '+literal(a['extraction_method'])]
        from .ranking import relation_polarity
        if a['predicate']=='has_phenotype': props.append('nova:polarity '+literal(relation_polarity(a)))
        if a.get('frequency_label') is not None: props.append('nova:frequencyLabel '+literal(a['frequency_label']))
        if a.get('references'): props.append('nova:references '+literal(json.dumps(a['references'],ensure_ascii=False)))
        if a.get('upstream_conditions'): props.append('nova:upstreamConditions '+literal(json.dumps(a['upstream_conditions'],ensure_ascii=False)))
        if a['reviewer']: props.append('nova:reviewer '+literal(a['reviewer']))
        lines.append(iri(a['id'])+' '+ ' ; '.join(props)+' .')
    lines.append(f'nova:snapshot nova:dataVersion {literal(kb.version)} ; nova:sha256 {literal(kb.sha256)} .')
    return '\n'.join(lines)+'\n'
