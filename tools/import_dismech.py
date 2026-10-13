"""Import explicit DisMech relationships from a pinned local checkout (safe YAML).
No evidence snippets, inferred phenotype chains, or clinical approval are imported.
"""
import argparse, gzip, hashlib, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import yaml
from meddb.terminology import read_obo

def run(repo, hpo_path, version_name, limit=None):
    root=Path(__file__).resolve().parents[1]; repo=Path(repo)
    if not re.fullmatch(r"meddb-\d{4}\.\d{2}\.\d{2}\.\d+", version_name): raise ValueError("Invalid release name")
    if (root/"data/releases"/(version_name+".json")).exists() or (root/"data/releases"/(version_name+".json.gz")).exists(): raise ValueError("Release already exists; choose a new version")
    version=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    d=json.loads((root/'data/releases/meddb-2026.10.10.3.json').read_text())
    d['version']=version_name;d['scope']='medical-knowledge-explorer'
    nodes={n['id']:n for n in d['concepts']}; sources={s['id']:s for s in d['sources']}
    hp=read_obo(hpo_path);terms=hp['terms']
    if hp['version'] != 'hp/releases/2026-09-01': raise ValueError('This importer base requires the pinned 2026-09-01 HPO snapshot')
    existing_hp={m['target']:n['id'] for n in nodes.values() for m in n['mappings'] if m['relation']=='exact'}
    names_ko={'Wilson Disease':'윌슨병','Wilsons Disease':'윌슨병','Asthma':'천식','Diabetes Mellitus Type 2':'제2형 당뇨병','Type 2 Diabetes Mellitus':'제2형 당뇨병','Type 1 Diabetes Mellitus':'제1형 당뇨병','Rheumatoid Arthritis':'류마티스 관절염','Systemic Lupus Erythematosus':'전신 홍반 루푸스','Alzheimer Disease':'알츠하이머병','Parkinson Disease':'파킨슨병','Cystic Fibrosis':'낭성 섬유증','Marfan Syndrome':'마르판 증후군','Down Syndrome':'다운 증후군','Acute Pancreatitis':'급성 췌장염','Chronic Pancreatitis':'만성 췌장염','Ulcerative Colitis':'궤양성 대장염','Liver Cirrhosis':'간경변증','Huntington Disease':'헌팅턴병','Multiple Sclerosis':'다발성 경화증','Gaucher Disease':'고셔병','Fabry Disease':'파브리병','Fanconi Anemia':'판코니 빈혈','Sickle Cell Disease':'겸상적혈구병','Hemophilia A':'혈우병 A','Hemophilia B':'혈우병 B','Psoriasis':'건선','Atopic Dermatitis':'아토피 피부염','Tuberculosis':'결핵','Hypertension':'고혈압','Osteoporosis':'골다공증','Epilepsy':'뇌전증','Migraine':'편두통','Obesity':'비만','Hypothyroidism':'갑상선 기능저하증','Hyperthyroidism':'갑상선 기능항진증','Graves Disease':'그레이브스병','Hashimoto Thyroiditis':'하시모토 갑상선염','Acute Appendicitis':'급성 충수염','Appendicitis':'충수염','Acute Myeloid Leukemia':'급성 골수성 백혈병','Sepsis':'패혈증','Celiac Disease':'셀리악병','Crohn Disease':'크론병','Irritable Bowel Syndrome':'과민성 장증후군'}
    hpko={'HP:0000952':'황달','HP:0002240':'간비대','HP:0001744':'비장비대','HP:0001251':'운동실조','HP:0001337':'진전','HP:0001250':'발작','HP:0001252':'근긴장 저하','HP:0001257':'경직','HP:0002090':'폐렴','HP:0002094':'호흡곤란','HP:0000978':'멍이 잘 듦','HP:0001878':'용혈성 빈혈','HP:0001873':'혈소판 감소증','HP:0001876':'범혈구 감소증','HP:0004322':'저신장','HP:0001249':'지적 장애','HP:0001263':'전반적 발달 지연','HP:0001276':'운동기능 저하','HP:0001626':'심장 형태 이상','HP:0001639':'비대성 심근병증','HP:0001635':'심부전','HP:0002020':'위식도 역류','HP:0000093':'단백뇨'}
    mechko={'Copper Accumulation':'구리 축적','Hepatic Copper Accumulation':'간 내 구리 축적','Oxidative Stress':'산화 스트레스','Inflammation':'염증','Chronic Inflammation':'만성 염증','Fibrosis':'섬유화','Hepatic Fibrosis':'간 섬유화','Mitochondrial Dysfunction':'미토콘드리아 기능 이상','Dysregulated Immune Response':'면역 반응 조절 이상','Neurodegeneration':'신경퇴행','Insulin Resistance':'인슐린 저항성','Autoimmune Response':'자가면역 반응','Airway Inflammation':'기도 염증','ATP7B Copper-Trafficking Defect':'ATP7B 구리 수송 결함','Impaired Biliary Copper Excretion':'담즙을 통한 구리 배설 장애','Impaired Ceruloplasmin Metallation':'세룰로플라스민 금속화 장애','Hepatocellular Injury':'간세포 손상'}
    merge={'Crohn Disease':'nova:crohns','Celiac Disease':'nova:celiac','Irritable Bowel Syndrome':'nova:ibs','Acute Pancreatitis':'nova:acute-pancreatitis','Appendicitis':'nova:appendicitis'}
    manifest=[]
    def addnode(id,kind,label,ko=None):
        if id not in nodes:nodes[id]=dict(id=id,kind=kind,label_ko=ko or label,label_en=label,aliases=[],mappings=[],label_origin='ai_translation_draft' if ko else 'upstream_english')
        return id
    def assertion(s,p,o,sid,loc,entry):
        refs=[e['reference'] for e in entry.get('evidence',[]) if isinstance(e,dict) and e.get('supports')=='SUPPORT' and e.get('reference')]
        row = dict(id=f'dismech-assertion:{len(d["assertions"]):06}',subject=s,predicate=p,object=o,source_id=sid,locator=loc,context=str(entry.get('description') or entry.get('notes') or ''),frequency=None,frequency_label=entry.get('frequency'),references=list(dict.fromkeys(refs)),extraction_method='upstream_import',review_status='draft',reviewer=None)
        if p == 'has_phenotype':
            row['polarity'] = 'excluded' if str(entry.get('frequency','')).strip().upper()=='EXCLUDED' else 'associated'
        row['upstream_conditions'] = {key:entry[key] for key in ('modifier','onset','severity','sex','notes') if key in entry}
        d['assertions'].append(row)
    files=sorted((repo/'kb/disorders').glob('*.yaml'))
    if limit:files=files[:limit]
    for file in files:
        raw=file.read_bytes();obj=yaml.load(raw,Loader=yaml.CSafeLoader)
        if not isinstance(obj,dict) or not obj.get('name'):continue
        name=str(obj['name']);sid='dismech:'+file.stem;did=merge.get(name,'dismech-disease:'+file.stem)
        addnode(did,'Disease',name,names_ko.get(name));nodes[did]['description']=str(obj.get('description') or '');nodes[did]['category']=str(obj.get('category') or '')
        sources[sid]=dict(id=sid,url=f'https://github.com/monarch-initiative/dismech/blob/{version}/kb/disorders/{file.name}',title='DisMech · '+name,accessed='2026-10-10',version=version,sha256=hashlib.sha256(raw).hexdigest(),redistribution='CC-BY-4.0 data; BSD-3-Clause repository notice retained')
        term=(obj.get('disease_term') or {}).get('term') or {}
        if term.get('id','').startswith('MONDO:'):
            nodes[did]['mappings'].append(dict(target=term['id'],target_label=term.get('label',name),relation='exact',source_id=sid,source_version=version,identifier_verified=False,review_status='draft',reviewer=None))
        for alias in obj.get('synonyms',[]) or []:
            if isinstance(alias,str) and alias not in nodes[did]['aliases']:nodes[did]['aliases'].append(alias)
        patho={};phenos={}
        for i,m in enumerate(obj.get('pathophysiology',[]) or []):
            if not isinstance(m,dict) or not m.get('name'):continue
            mid='dismech-mechanism:'+file.stem+':'+str(i);mn=str(m['name']);addnode(mid,'Mechanism',mn,mechko.get(mn));nodes[mid]['description']=str(m.get('description') or '');patho[mn]=mid
            assertion(did,'has_mechanism',mid,sid,f'pathophysiology[{i}]',m)
        for i,p in enumerate(obj.get('phenotypes',[]) or []):
            if not isinstance(p,dict) or not p.get('name'):continue
            term=(p.get('phenotype_term') or {}).get('term') or {};hid=term.get('id');pn=str(p['name'])
            if hid in terms and not terms[hid]['obsolete']:
                fid=existing_hp.get(hid,'hpo:'+hid);addnode(fid,'Finding',terms[hid]['label'],hpko.get(hid));existing_hp[hid]=fid
                if not nodes[fid]['mappings']:nodes[fid]['mappings'].append(dict(target=hid,target_label=terms[hid]['label'],relation='exact',source_id='hpo-2026-09-01',source_version=hp['version'],identifier_verified=True,review_status='draft',reviewer=None))
            else:
                fid='dismech-finding:'+file.stem+':'+str(i);addnode(fid,'Finding',pn)
            phenos[pn]=fid
            if pn not in nodes[fid]['aliases']:nodes[fid]['aliases'].append(pn)
            assertion(did,'has_phenotype',fid,sid,f'phenotypes[{i}]',p)
        for i,m in enumerate(obj.get('pathophysiology',[]) or []):
            if not isinstance(m,dict) or m.get('name') not in patho:continue
            for j,target in enumerate(m.get('downstream',[]) or []):
                if not isinstance(target,dict):continue
                targetname=target.get('target');tid=patho.get(targetname) or phenos.get(targetname)
                if tid:assertion(patho[m['name']],'causes',tid,sid,f'pathophysiology[{i}].downstream[{j}]',target)
        manifest.append(dict(file=file.name,sha256=sources[sid]['sha256']))
    d['concepts']=list(nodes.values());d['sources']=list(sources.values())
    text=json.dumps(d,ensure_ascii=False,separators=(',',':'))+'\n';(root/'data/releases'/f'{d["version"]}.json.gz').write_bytes(gzip.compress(text.encode(),mtime=0))
    (root/'data/terminology/dismech-manifest.json').write_text(json.dumps(dict(repository='https://github.com/monarch-initiative/dismech',commit=version,files=manifest,transform='Explicit disease-to-mechanism, phenotype and downstream links only; citations retained, quotations omitted; local review remains draft'),indent=2)+'\n')
    print('Imported',len(manifest),'files;',len(nodes),'concepts;',len(d['assertions']),'assertions')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('repo');parser.add_argument('hpo');parser.add_argument('--version',required=True);parser.add_argument('--limit',type=int);args=parser.parse_args();run(args.repo,args.hpo,args.version,args.limit)
