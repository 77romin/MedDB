"""Preserve official archives and map document titles to concepts, never patient answers."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB

ROOT=Path(__file__).resolve().parents[1]
EXPECTED='ef58c2f4369750af382f2706dcc1c9c7a85e3a93c261d880f7470d695eaf30d5'


def unpack(path,name,expected=None):
    raw=Path(path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if expected and digest!=expected:raise ValueError('Official archive SHA256 mismatch')
    folder=ROOT/'data/external'/name;folder.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,folder/'original.zip')
    entries=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        seen=set()
        for info in archive.infolist():
            target=(folder/info.filename).resolve()
            if not target.is_relative_to(folder.resolve()) or info.filename in seen:raise ValueError('Unsafe/duplicate archive path')
            seen.add(info.filename)
            if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            data=archive.read(info);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            entries.append({'path':info.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'archive_sha256':digest,'archive_bytes':len(raw),'files':entries,'verified':all(hashlib.sha256((folder/e['path']).read_bytes()).hexdigest()==e['sha256'] for e in entries)}
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return folder,manifest


def run(guidelines,samples,starter):
    folder,manifest=unpack(guidelines,'guidelines',EXPECTED)
    sample_folder,sample_manifest=unpack(samples,'samples')
    starter_folder,starter_manifest=unpack(starter,'starter')
    catalog=folder/'guidelines/catalog.csv'
    with catalog.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    kb=KB();terms={}
    for n in kb.nodes.values():
        if n['kind']!='Disease':continue
        for label in [n['label_en'],n['label_ko'],*n['aliases']]:
            normalized=' '.join(re.findall(r'\w+',label.casefold()))
            if len(normalized)>=4 and len(normalized.split())<=10:terms.setdefault(normalized,set()).add(n['id'])
    documents=[];links=[]
    hashes={e['path'].removeprefix('guidelines/'):e['sha256'] for e in manifest['files']}
    for row in rows:
        path=row['파일명'];title=row['제목'];words=re.findall(r'\w+',title.casefold());matched=set()
        for start in range(len(words)):
            for length in range(1,min(10,len(words)-start)+1):matched.update(terms.get(' '.join(words[start:start+length]),()))
        documents.append({'id':'nova-guideline:'+path,'path':path,'title':title,'organization':row['발행기관'],'year':row['연도'],'language':row['언어'],'document_type':row['문서 유형'],'license':row['라이선스'],'source_url':row['출처 URL'],'sha256':hashes.get(path)})
        for concept in sorted(matched):links.append({'subject':concept,'predicate':'has_reference_candidate','object':'nova-guideline:'+path,'review_status':'draft','method':'exact normalized title phrase; not clinical relationship or confirmed document relevance'})
    extension={'format':'nova-evidence-layer-1','base_version':kb.version,'base_sha256':kb.sha256,'guidelines_archive_sha256':EXPECTED,'documents':documents,'links':links,'interpretation':'Document metadata and tentative title links; no disease-finding assertions extracted. Restricted-license source bodies are not redistributed.'}
    (ROOT/'data/agent/guideline-links.json.gz').write_bytes(gzip.compress(json.dumps(extension,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    sample_summary=[]
    for path in sorted((sample_folder/'nova-samples-2026').glob('*/model_record.json')):
        record=json.loads(path.read_text(encoding='utf-8'));diagnosis=record.get('diagnosis') or record.get('A',{}).get('diagnosis')
        sample_summary.append({'case':path.parent.name,'reference_diagnosis':diagnosis,'evaluation_only':True})
    summary={'source_url':'https://nova.snubhai.org/docs/','downloaded':'2026-10-13','official_archive_hash_verified':manifest['archive_sha256']==EXPECTED,'all_original_parts_verified':manifest['verified'] and sample_manifest['verified'] and starter_manifest['verified'],'documents':len(documents),'title_links':len(links),'linked_diseases':len({l['subject'] for l in links}),'samples':sample_summary,'notes':'Original guidelines, SDK and sample answers are local-only. Samples are excluded from runtime knowledge bundle.'}
    (ROOT/'docs/nova-resource-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--guidelines',required=True);p.add_argument('--samples',required=True);p.add_argument('--starter',required=True);a=p.parse_args();run(a.guidelines,a.samples,a.starter)
