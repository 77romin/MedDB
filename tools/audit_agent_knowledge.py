"""Generate coverage and review queues without approving medical assertions."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB
from meddb.ranking import relation_polarity
from meddb.workflow import resource, resolve, profile_kb


def run():
    kb=KB()
    phrases,_=resource('phrases.json')
    coverage=[]
    for entry in phrases['entries']:
        ids=resolve(kb,entry)
        disease_ids={a['subject'] for a in kb.data['assertions'] if a['predicate']=='has_phenotype' and a['object'] in ids and relation_polarity(a)=='associated'}
        coverage.append({'phrases':entry['phrases'],'finding_ids':ids,'disease_count':len(disease_ids),'status':'mapped_draft' if ids else 'missing'})
    queue=[{'assertion_id':a['id'],'disease':kb.nodes[a['subject']]['label_en'],'finding':kb.nodes[a['object']]['label_en'],'source_id':a['source_id'],'locator':a['locator'],'context':a['context'],'polarity':relation_polarity(a),'review_status':a['review_status']} for a in kb.data['assertions'] if a['predicate']=='has_phenotype' and relation_polarity(a)=='excluded']
    profiles={name:profile_kb(kb,name)[1] for name in ('reviewed','pilot','research')}
    release=KB(version=kb.version)
    report={'data_version':kb.version,'data_sha256':kb.sha256,'release_consistency':{'release_sha256':release.sha256,'byte_hash_equal':kb.sha256==release.sha256,'json_content_equal':kb.data==release.data},'profiles':profiles,'coverage':coverage,'clinical_review_queue':queue,'competition_example_gap':{'source':'docs/nova_competition/deck_01/slides.md, slides 14 and 20','diagnosis':'수면제 의존','search_terms':['Sedative','Hypnotic'],'found_ids':[n['id'] for term in ('Sedative','Hypnotic') for n in kb.search(term,'Disease')],'status':'needs terminology and disease coverage review; no diagnosis rule generated from one case'}}
    target=Path(__file__).resolve().parents[1]/'docs'/'agent-knowledge-audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'phrases':len(coverage),'mapped':sum(bool(c['finding_ids']) for c in coverage),'excluded_review_queue':len(queue),'profiles':{n:p['assertions'] for n,p in profiles.items()}},ensure_ascii=True))


if __name__=='__main__':run()
