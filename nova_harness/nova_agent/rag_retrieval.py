"""R2 retrieval-only experiment on the unchanged R1 index and encoder.

Metadata BM25 expands recall; exact term coverage reranks verified excerpts.
No patient facts, neural reranker, extra Doctor calls, or MMR are introduced.
"""
from collections import Counter
import hashlib
import json
import re
import sqlite3

from .rag import VectorStore as R1Store


GENERIC = {'disease', 'diseases', 'disorder', 'disorders', 'syndrome', 'syndromes',
           'management', 'treatment', 'guideline', 'guidelines', 'clinical', 'patient',
           'patients', 'condition', 'acute', 'chronic', 'unspecified', 'other', 'with',
           'and', 'the', 'of', 'in', 'for', 'due', '질환', '장애', '증후군', '치료', '관리'}


def keywords(text):
    return {t for t in re.findall(r'[a-z][a-z0-9-]+|[가-힣]+', text.lower())
            if len(t) >= 2 and t not in GENERIC}


class VectorStore(R1Store):
    def __init__(self, path, corpus=None):
        super().__init__(path, corpus)
        self.metadata = [json.loads(raw) for _, raw in self.rows]
        self.lexical = sqlite3.connect(':memory:')
        self.fts = True
        try:
            self.lexical.execute('create virtual table titles using fts5(title,heading)')
            self.lexical.executemany('insert into titles(rowid,title,heading) values(?,?,?)',
                                    [(i+1, m['title'], m.get('heading','')) for i, m in enumerate(self.metadata)])
        except sqlite3.OperationalError:
            self.fts = False

    def close(self):
        self.lexical.close()
        super().close()

    def search(self, query, k=3, minimum=0.3):
        if not isinstance(query, str) or not query.strip() or len(query) > 4000 or not 1 <= k <= 10:
            raise ValueError('invalid query or k')
        np = self.np
        anchors = keywords(query)
        if not anchors:
            self.audit.append({'query':query, 'chunk_ids':[], 'reason':'no_specific_terms'})
            return []
        cosine = self.vectors @ self.embed(query)
        dense = list(map(int, np.argsort(-cosine, kind='stable')[:200]))
        if self.fts:
            match = ' OR '.join('"'+word+'"' for word in sorted(anchors))
            sparse = [r[0]-1 for r in self.lexical.execute(
                'select rowid from titles where titles match ? order by bm25(titles,5,2),rowid limit 200', (match,))]
        else:
            # Runtime portability: deterministic metadata overlap if FTS5 is absent.
            sparse = sorted(range(len(self.metadata)), key=lambda i:(
                -len(anchors & keywords(self.metadata[i]['title']+' '+self.metadata[i].get('heading',''))), i))[:200]
        fusion = {}
        for ranking in (dense, sparse):
            for rank, idx in enumerate(ranking, 1):
                fusion[idx] = fusion.get(idx, 0)+1/(60+rank)
        weights = {t: float(self.idf[self.vocab[t]]) if t in self.vocab else 8.0 for t in anchors}
        total = sum(weights.values())
        cache = {}
        candidates = []
        rejected = Counter()
        for idx, rrf in sorted(fusion.items(), key=lambda pair:(-pair[1],pair[0])):
            meta = self.metadata[idx]
            title_matches = anchors & keywords(meta['title'])
            # A passing mention inside an unrelated disease guideline is insufficient.
            if not title_matches:
                rejected['title_mismatch'] += 1
                continue
            heading = meta.get('heading', '').lower()
            if re.search(r'\b(references|bibliography|acknowledg\w*|conflict\w*|funding)\b|참고문헌|이해상충', heading):
                rejected['nonclinical_section'] += 1
                continue
            path = (self.root/meta['path']).resolve()
            if not path.is_relative_to(self.root):
                rejected['unsafe_path'] += 1
                continue
            if meta['path'] not in cache:
                try:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != meta['sha256']:
                        cache[meta['path']] = None
                    else:
                        cache[meta['path']] = raw.decode('utf-8').splitlines(keepends=True)
                except (OSError, UnicodeError):
                    cache[meta['path']] = None
            lines = cache[meta['path']]
            if lines is None:
                rejected['source_unavailable_or_changed'] += 1
                continue
            excerpt = ''.join(lines[meta['start']:meta['end']])
            body_matches = anchors & keywords(excerpt)
            if not body_matches or len(excerpt) > 7000:
                rejected['excerpt_mismatch_or_size'] += 1
                continue
            # Sparse candidates may recover rare entities missed by low-rank LSA.
            # They must have verified title AND body support rather than meet a
            # cosine threshold calibrated for dense candidates only.
            if cosine[idx] < minimum and len(body_matches & title_matches) == 0:
                rejected['weak_candidate'] += 1
                continue
            title_coverage = sum(weights[t] for t in title_matches)/total
            body_coverage = sum(weights[t] for t in body_matches)/total
            section_coverage = sum(weights[t] for t in anchors & keywords(heading))/total
            score = 0.45*title_coverage+0.25*body_coverage+0.1*section_coverage+0.15*max(float(cosine[idx]),0)+0.05*rrf/(2/61)
            year = re.search(r'(?:19|20)\d{2}', str(meta.get('year','')))
            year = int(year.group()) if year else 0
            candidates.append((score, year, self.rows[idx][0], dict(
                meta, chunk_id=self.rows[idx][0], cosine=round(float(cosine[idx]),6),
                retrieval_score=round(score,6), retrieval_method='metadata_bm25+cosine+coverage',
                excerpt=excerpt)))
        results = []
        seen = set()
        for _, _, _, item in sorted(candidates, key=lambda x:(-x[0],-x[1],x[2])):
            if item['path'] in seen:
                continue
            results.append(item)
            seen.add(item['path'])
            if len(results) == k:
                break
        self.audit.append({'query':query, 'chunk_ids':[r['chunk_id'] for r in results],
                           'dense_candidates':len(dense), 'lexical_candidates':len(sparse),
                           'rejected':dict(rejected), 'fts5':self.fts})
        return results
