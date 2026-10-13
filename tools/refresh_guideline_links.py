"""Refresh tentative metadata links after a medical snapshot update; do not reread bodies."""
import gzip
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from meddb import KB


def run():
    root=Path(__file__).resolve().parents[1];path=root/'data/agent/guideline-links.json.gz'
    layer=json.loads(gzip.decompress(path.read_bytes()));kb=KB();terms={}
    for node in kb.nodes.values():
        if node['kind']!='Disease':continue
        for label in [node['label_en'],node['label_ko'],*node['aliases']]:
            label=' '.join(re.findall(r'\w+',label.casefold()))
            if len(label)>=4 and len(label.split())<=10:terms.setdefault(label,set()).add(node['id'])
    links=[]
    for doc in layer['documents']:
        words=re.findall(r'\w+',doc['title'].casefold());ids=set()
        for start in range(len(words)):
            for length in range(1,min(10,len(words)-start)+1):ids.update(terms.get(' '.join(words[start:start+length]),()))
        links.extend({'subject':node,'predicate':'has_reference_candidate','object':doc['id'],'review_status':'draft','method':'exact normalized title phrase; not clinical relationship or confirmed document relevance'} for node in sorted(ids))
    layer.update(base_version=kb.version,base_sha256=kb.sha256,links=links)
    path.write_bytes(gzip.compress(json.dumps(layer,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    summary_path=root/'docs/nova-resource-summary.json';summary=json.loads(summary_path.read_text(encoding='utf-8'));summary.update(title_links=len(links),linked_diseases=len({a['subject'] for a in links}),base_version=kb.version)
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'links':len(links),'diseases':summary['linked_diseases'],'base_version':kb.version}))


if __name__=='__main__':run()
