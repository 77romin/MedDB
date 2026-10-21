"""Inspect fixed engineering queries, not clinical scores or held-out evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nova_agent.rag import VectorStore as R1
from nova_agent.rag_retrieval import VectorStore as R2

QUERIES=['asthma','Graves hyperthyroidism','insomnia benzodiazepine dependence',
         'hypertension','diabetes mellitus','rheumatoid arthritis','tuberculosis',
         'epilepsy','migraine','성장 지연']


def compare():
    path=ROOT/'dist/rag/index.sqlite'
    stores=[R1(path,ROOT/'vendor/guidelines/guidelines'),R2(path,ROOT/'vendor/guidelines/guidelines')]
    rows=[]
    try:
        for query in QUERIES:
            row={'query':query}
            for name,store in zip(('r1','r2'),stores):
                start=time.monotonic(); found=store.search(query,k=2)
                row[name]={'seconds':round(time.monotonic()-start,4),
                           'results':[{'title':r['title'],'chunk_id':r['chunk_id']} for r in found]}
            rows.append(row)
    finally:
        for store in stores:store.close()
    return {'index_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'purpose':'engineering regression queries; not held-out accuracy or clinical performance',
            'queries':rows}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out');args=p.parse_args()
    result=json.dumps(compare(),ensure_ascii=False,indent=2)
    if args.out:Path(args.out).write_text(result,encoding='utf-8')
    print(result)
