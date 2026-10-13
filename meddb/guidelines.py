"""Read-only retrieval from the official runtime corpus; no patient answers or network."""
import csv
import hashlib
import os
from pathlib import Path
import re
import sqlite3

DEFAULT_ROOT=Path(__file__).resolve().parents[1]/'data/external/guidelines/guidelines'


class Guidelines:
    def __init__(self,root=None):
        self.root=Path(root or os.environ.get('NOVA_GUIDELINES_DIR') or DEFAULT_ROOT).resolve()
        self.rows=[];self.available=(self.root/'catalog.csv').exists()
        self.index=None
        if not self.available:return
        with (self.root/'catalog.csv').open(encoding='utf-8-sig',newline='') as stream:self.rows=list(csv.DictReader(stream))
        # Small metadata-only index; no filesystem writes and no /tmp quota requirement.
        self.index=sqlite3.connect(':memory:',check_same_thread=False)
        self.index.execute('CREATE VIRTUAL TABLE titles USING fts5(title, organization, type)')
        self.index.executemany('INSERT INTO titles(rowid,title,organization,type) VALUES(?,?,?,?)',[(i+1,r['제목'],r['발행기관'],r['문서 유형']) for i,r in enumerate(self.rows)])

    def search(self,query,limit=3):
        if not isinstance(query,str) or not query.strip() or len(query)>500 or type(limit) is not int or not 1<=limit<=10:raise ValueError('Invalid guideline query/limit')
        if not self.available:return {'available':False,'documents':[],'reason':'Set NOVA_GUIDELINES_DIR to the official extracted guidelines directory.'}
        tokens=re.findall(r'\w+',query.casefold())[:20]
        if not tokens:return {'available':True,'documents':[],'catalog_documents':len(self.rows)}
        match=' OR '.join('"'+t+'"' for t in tokens)
        scored={i-1:-score for i,score in self.index.execute('SELECT rowid,bm25(titles,5,1,2) FROM titles WHERE titles MATCH ? ORDER BY bm25(titles,5,1,2) LIMIT ?',(match,limit*5))}
        # Korean titles often join words; substring fallback preserves 2-character queries.
        for i,row in enumerate(self.rows):
            title=row['제목'].casefold()
            if any(t in title for t in tokens):
                scored[i]=scored.get(i,0)+sum(t in title for t in tokens)
                if row['문서 유형']=='진료지침':scored[i]+=2
                if len(title)>=8 and title in query.casefold():scored[i]+=4
                if 'archived' in title:scored[i]-=5
        documents=[]
        for i,score in sorted(scored.items(),key=lambda x:(-x[1],self.rows[x[0]]['파일명']))[:limit]:
            row=self.rows[i];path=(self.root/row['파일명']).resolve()
            if not path.is_relative_to(self.root):raise ValueError('Unsafe guideline path')
            if not path.is_file():continue
            raw=path.read_bytes();text=raw.decode('utf-8');lines=text.splitlines()
            # Return original excerpts with line provenance; full document remains accessible locally.
            start=next((j for j,line in enumerate(lines) if j>15 and any(t in line.casefold() for t in tokens)),0)
            excerpt_lines=[];size=0
            for line in lines[start:]:
                if size+len(line)+1>2400:
                    if not excerpt_lines:excerpt_lines.append(line[:2400])
                    break
                excerpt_lines.append(line);size+=len(line)+1
            excerpt='\n'.join(excerpt_lines)
            documents.append({'title':row['제목'],'path':row['파일명'],'organization':row['발행기관'],'year':row['연도'],'language':row['언어'],'license':row['라이선스'],'source_url':row['출처 URL'],'sha256':hashlib.sha256(raw).hexdigest(),'score':round(score,6),'excerpt':excerpt,'start_line':start+1,'end_line':start+len(excerpt_lines),'end_column':len(excerpt_lines[-1]) if excerpt_lines else 0,'excerpt_only':True,'local_path':str(path),'interpretation':'Original source excerpt; relevance is lexical retrieval, not confirmed medical support.'})
        return {'available':True,'catalog_documents':len(self.rows),'query':query,'documents':documents,'retrieval':'metadata lexical search; source bodies preserved without alteration'}
