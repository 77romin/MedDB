"""Coverage audit only; sample scripts/answers never enter the runtime bundle."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB

ROOT=Path(__file__).resolve().parents[1]


def run():
    kb=KB();base=KB(version='meddb-2026.10.10.4');mapping={
        'C01':{'terms':['Sedative','Hypnotic'],'query':'hypnotic insomnia'},
        'C03':{'terms':['Constitutional Delay','체질성 성장'],'query':'constitutional delay growth puberty'},
        'C10':{'terms':['Graves Disease','Graves_Disease','그레이브스'],'query':'Graves Disease'}
    };results=[]
    for case,queries in mapping.items():
        folder=ROOT/'data/external/samples/nova-samples-2026'/case
        sample=json.loads((folder/'case.json').read_text(encoding='utf-8'))
        record=json.loads((folder/'model_record.json').read_text(encoding='utf-8'))
        matching={n['id']:n for term in queries['terms'] for n in kb.search(term,'Disease')}
        baseline={n['id']:n for term in queries['terms'] for n in base.search(term,'Disease')}
        normalized=kb.normalize(sample['start_information']['opening'])
        source=kb.guidelines(queries['query'])
        results.append({'case':case,'reference_diagnosis':record.get('diagnosis') or record.get('A',{}).get('diagnosis'),'base_matching_disease_ids':sorted(baseline),'matching_disease_ids':sorted(matching),'starting_information_mapped_mentions':len(normalized['mentions']),'guideline_query':queries['query'],'retrieved_documents':[{'title':d['title'],'path':d['path'],'source_url':d['source_url'],'license':d['license']} for d in source['documents']],'purpose':'Offline terminology/reference coverage only; query uses reference diagnosis and is not a prospective diagnosis test.'})
    report={'scope':'public sample coverage, not diagnosis accuracy','base_version':base.version,'new_version':kb.version,'cases':results,'actual_agent_diagnosis_evaluation':'not_run; no calls to paid model APIs or team credentials','sample_answers_in_runtime_bundle':False}
    (ROOT/'docs/public-sample-coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(results),'disease_names_found':sum(bool(r['matching_disease_ids']) for r in results),'with_guideline_results':sum(bool(r['retrieved_documents']) for r in results)},ensure_ascii=True))


if __name__=='__main__':run()
