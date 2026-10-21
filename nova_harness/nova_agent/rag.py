"""Offline LSA embeddings and exact cosine search over a read-only SQLite store.

LSA is a corpus-trained statistical embedding, not a pretrained neural encoder.
Only provenance and derived vectors are packaged; excerpts come from the corpus.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3


def tokens(text):
    result = re.findall(r"[a-z][a-z0-9-]+|[가-힣]+", text.lower())
    return result + [word[i:i+2] for word in result if re.fullmatch(r"[가-힣]+", word)
                     for i in range(len(word)-1)]


def chunks(text, limit=3600):
    """Line-addressed sections; retain heading context, never silently truncate."""
    lines = text.splitlines(keepends=True)
    start = 0
    if lines and lines[0].strip() == '---':
        start = next((i+1 for i in range(1, len(lines)) if lines[i].strip() == '---'), 0)
    heading = ''
    buf = []
    begin = start
    for i in range(start, len(lines)):
        line = lines[i]
        if buf and ((line.startswith('#') and sum(map(len, buf)) >= 80) or sum(map(len, buf))+len(line) > limit):
            yield begin, i, heading, ''.join(buf)
            buf = []
            begin = i
        if line.startswith('#'):
            heading = line.strip()
        buf.append(line)
    if buf:
        yield begin, len(lines), heading, ''.join(buf)


class VectorStore:
    def __init__(self, path, corpus=None):
        import numpy as np
        self.np = np
        self.root = Path(corpus or os.environ.get('NOVA_GUIDELINES_DIR', '/opt/nova/guidelines')).resolve()
        self.db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
        self.meta = dict(self.db.execute('select key,value from meta'))
        self.dim = int(self.meta['dimensions'])
        terms = list(self.db.execute('select token,idf,projection from terms order by id'))
        self.vocab = {row[0]: i for i, row in enumerate(terms)}
        self.idf = np.array([row[1] for row in terms], dtype=np.float32)
        self.projection = np.vstack([np.frombuffer(row[2], dtype='<f4') for row in terms])
        self.rows = list(self.db.execute('select id,metadata,vector from chunks order by id'))
        self.vectors = np.vstack([np.frombuffer(row[2], dtype=self.meta.get('vector_dtype', '<f4')) for row in self.rows]).astype(np.float32)
        self.vectors /= np.maximum(np.linalg.norm(self.vectors, axis=1, keepdims=True), 1e-12)
        self.rows = [(cid, meta) for cid, meta, _ in self.rows]
        self.audit = []

    def close(self):
        self.db.close()

    def embed(self, text):
        np = self.np
        vector = np.zeros(len(self.vocab), dtype=np.float32)
        for term, count in Counter(tokens(text)).items():
            if term in self.vocab:
                i = self.vocab[term]
                vector[i] = (1+np.log(count))*self.idf[i]
        norm = np.linalg.norm(vector)
        if not norm:
            return np.zeros(self.dim, dtype=np.float32)
        latent = (vector/norm) @ self.projection
        return latent/max(float(np.linalg.norm(latent)), 1e-12)

    def search(self, query, k=3, minimum=0.3):
        if not isinstance(query, str) or not query.strip() or not 1 <= k <= 10:
            raise ValueError('invalid query or k')
        np = self.np
        vector = self.embed(query[:4000])
        scores = self.vectors @ vector
        results = []
        seen = set()
        generic = {'disease','treatment','management','follow','condition','evaluation','clinical',
                   'syndrome','disorder','guideline','guidelines','patient','chronic','acute'}
        anchors = {t for t in re.findall(r'[a-z][a-z0-9-]+|[가-힣]+', query.lower())
                   if (len(t) >= 4 or (re.fullmatch(r'[가-힣]+', t) and len(t) >= 2)) and t not in generic}
        cache = {}
        # Verify a bounded candidate set; changed/missing sources never yield excerpts.
        for idx in np.argsort(-scores, kind='stable')[:max(k*20, 60)]:
            score = float(scores[idx])
            if score < minimum:
                break
            cid, raw = self.rows[int(idx)]
            meta = json.loads(raw)
            if meta['path'] in seen:
                continue
            path = (self.root/meta['path']).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                continue
            if meta['path'] not in cache:
                cache[meta['path']] = path.read_bytes()
            data = cache[meta['path']]
            if hashlib.sha256(data).hexdigest() != meta['sha256']:
                continue
            lines = data.decode('utf-8').splitlines(keepends=True)
            excerpt = ''.join(lines[meta['start']:meta['end']])
            if len(excerpt) > 7000:
                continue
            # Low-rank similarity alone can confuse unrelated rare diseases.
            # Abstain unless a specific query term occurs in the actual excerpt.
            if not anchors or not anchors.intersection(re.findall(r'[a-z][a-z0-9-]+|[가-힣]+', excerpt.lower())):
                continue
            results.append(dict(meta, chunk_id=cid, cosine=round(score, 6), excerpt=excerpt))
            seen.add(meta['path'])
            if len(results) == k:
                break
        self.audit.append({'query': query[:4000], 'chunk_ids': [r['chunk_id'] for r in results],
                           'scores': [r['cosine'] for r in results]})
        return results
