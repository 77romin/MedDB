"""Small independently sourced draft addition, never a public-case answer lookup."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB

ROOT=Path(__file__).resolve().parents[1]
VERSION='meddb-2026.10.13.1'


def run():
    base=KB(version='meddb-2026.10.10.4')
    data=base.data;data['version']=VERSION
    sources=[
        {'id':'samhsa-dsm-change-2016','url':'https://www.ncbi.nlm.nih.gov/books/NBK519702/','title':'SAMHSA · Substance Use Disorders','version':'2016','accessed':'2026-10-13','redistribution':'Only bibliographic reference and independently stated facts; no diagnostic manual criteria reproduced.'},
        {'id':'cdgp-review-2022','url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC8944060/','title':'Current clinical management of constitutional delay of growth and puberty','version':'2022','accessed':'2026-10-13','redistribution':'CC BY 4.0; source identified and concepts/associations structured; no article body reproduced.'}
    ]
    additions=[
        {'id':'nova:sedative-hypnotic-use-disorder','kind':'Disease','label_ko':'진정·수면·항불안제 사용장애','label_en':'Sedative, Hypnotic, or Anxiolytic Use Disorder','aliases':['Sedative-Hypnotic Use Disorder'],'category':'Psychiatric','mappings':[],'label_origin':'ai_translation_draft','source_id':'samhsa-dsm-change-2016','description':'초안 개념. 약물 갈망 연관은 단일 단서이며 진단을 확정하지 않는다. 의학적 감독 아래의 신체 의존을 사용장애와 동일시하지 않는다.'},
        {'id':'nova:sedative-craving','kind':'Finding','label_ko':'진정·수면제 갈망','label_en':'Craving for sedative or hypnotic medication','aliases':[],'mappings':[],'label_origin':'ai_translation_draft'},
        {'id':'nova:constitutional-growth-delay','kind':'Disease','label_ko':'체질성 성장지연','label_en':'Constitutional Growth Delay','aliases':['Constitutional delay of growth and puberty'],'category':'Endocrine','mappings':[],'label_origin':'ai_translation_draft','source_id':'cdgp-review-2022','description':'초안 개념. 저신장·사춘기 및 골성숙 지연의 연관은 다른 원인과의 구분 및 임상 평가가 필요하다.'}
    ]
    assertions=[]
    for finding in ('hpo:HP:0004322','hpo:HP:0000823','hpo:HP:0002750'):
        assertions.append({'id':'nova-targeted:'+finding,'subject':'nova:constitutional-growth-delay','predicate':'has_phenotype','object':finding,'source_id':'cdgp-review-2022','locator':'Abstract / clinical description of CDGP','context':'청소년 성장·사춘기 지연 맥락의 연관. 단독 소견으로 확정하지 않으며 다른 원인의 평가가 필요하다.','frequency':None,'frequency_label':None,'polarity':'associated','references':['PMCID:PMC8944060'],'extraction_method':'source_based_manual_draft','review_status':'draft','reviewer':None})
    assertions.append({'id':'nova-targeted:sedative-craving','subject':'nova:sedative-hypnotic-use-disorder','predicate':'has_phenotype','object':'nova:sedative-craving','source_id':'samhsa-dsm-change-2016','locator':'2.5.7 Sedative, Hypnotic, or Anxiolytic Use Disorder','context':'공식 보고서의 craving 추가 설명에 따른 초안 연관. 단일 증상은 사용장애 확정 기준이 아니며 신체 의존과 사용장애를 구분한다.','frequency':None,'frequency_label':None,'polarity':'associated','references':[],'extraction_method':'source_based_manual_draft','review_status':'draft','reviewer':None})
    data['concepts'].extend(additions);data['sources'].extend(sources);data['assertions'].extend(assertions)
    raw=(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    target=ROOT/'data/releases'/f'{VERSION}.json.gz'
    if target.exists():
        if gzip.decompress(target.read_bytes())!=raw:raise ValueError('Refuse to overwrite a different frozen release')
    else:target.write_bytes(gzip.compress(raw,mtime=0))
    checked=KB(version=VERSION)
    summary={'version':VERSION,'sha256':checked.sha256,'base_version':base.version,'new_concepts':len(additions),'new_diseases':2,'new_assertions':len(assertions),'review_status':'all draft','source_basis':[s['url'] for s in sources],'sample_answers_used_to_create_relations':False,'diagnostic_accuracy_claim':None}
    (ROOT/'docs/targeted-release.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True))


if __name__=='__main__':run()
