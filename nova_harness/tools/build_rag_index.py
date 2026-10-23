"""Build corpus-derived LSA vectors; never includes sample answers or raw bodies."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nova_agent.rag import chunks, tokens


def build(root, out, dimensions=64):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from threadpoolctl import threadpool_limits
    root, out = Path(root).resolve(), Path(out)
    rows = list(csv.DictReader((root/'catalog.csv').open(encoding='utf-8-sig')))
    metadata, texts = [], []
    # Broad, case-independent scope: clinical guidelines, recommendations, consensus.
    selected = [r for r in rows if r['문서 유형'] in ('진료지침', '권고문', '합의문')]
    for row in selected:
        path = (root/row['파일명']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('unsafe corpus path')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        for start, end, heading, body in chunks(raw.decode('utf-8')):
            if not body.strip():
                continue
            meta = {'path': row['파일명'], 'title': row['제목'], 'organization': row['발행기관'],
                    'year': row['연도'], 'language': row['언어'], 'license': row['라이선스'],
                    'source_url': row['출처 URL'], 'sha256': digest,
                    'start': start, 'end': end, 'heading': heading}
            metadata.append(meta)
            texts.append(row['제목']+' '+heading+' '+body)
    print(json.dumps({'documents': len(selected), 'chunks': len(texts)}), flush=True)
    tf = TfidfVectorizer(analyzer=tokens, max_features=20000, min_df=2,
                         sublinear_tf=True, dtype=np.float32)
    with threadpool_limits(limits=2):
        matrix = tf.fit_transform(texts)
        svd = TruncatedSVD(n_components=dimensions, random_state=42, n_iter=5)
        vectors = svd.fit_transform(matrix)
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    db = sqlite3.connect(out)
    db.executescript('create table meta(key text primary key,value text);'
                     'create table terms(id integer primary key,token text,idf real,projection blob);'
                     'create table chunks(id text primary key,metadata text,vector blob);')
    manifest = {'format': 'nova-lsa-1', 'dimensions': str(dimensions), 'model': 'TF-IDF + TruncatedSVD (LSA)',
                'vector_dtype': 'i1',
                'catalog_sha256': hashlib.sha256((root/'catalog.csv').read_bytes()).hexdigest(),
                'documents': str(len(selected)), 'chunks': str(len(metadata)),
                'scope': 'all clinical guidelines, recommendations and consensus; no case selection',
                'explained_variance': str(float(svd.explained_variance_ratio_.sum()))}
    db.executemany('insert into meta values(?,?)', manifest.items())
    db.executemany('insert into terms values(?,?,?,?)',
                   [(i, term, float(tf.idf_[i]), svd.components_[:, i].astype('<f4').tobytes())
                    for i, term in enumerate(tf.get_feature_names_out())])
    db.executemany('insert into chunks values(?,?,?)',
                   [(hashlib.sha256((m['path']+':'+str(m['start'])+':'+m['sha256']).encode()).hexdigest()[:24],
                     json.dumps(m, ensure_ascii=False), np.round(v.astype('<f2').astype('f4')*127).astype('i1').tobytes()) for m, v in zip(metadata, vectors)])
    db.commit()
    db.close()
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    out.with_suffix('.manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default=str(ROOT/'vendor/guidelines/guidelines'))
    parser.add_argument('--out', default=str(ROOT/'dist/rag/index.sqlite'))
    args = parser.parse_args()
    build(args.corpus, args.out)
