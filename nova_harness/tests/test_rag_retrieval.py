import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional RAG dependency')
class RetrievalTests(unittest.TestCase):
    def test_sparse_recovery_rejects_incidental_mention_and_references(self):
        import numpy as np
        from nova_agent.rag_retrieval import VectorStore
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = sqlite3.connect(root/'index.db')
            db.executescript('create table meta(key,value);create table terms(id,token,idf,projection);'
                             'create table chunks(id,metadata,vector);')
            db.execute('insert into meta values(?,?)',('dimensions','2'))
            db.execute('insert into terms values(?,?,?,?)',(0,'asthma',1.,np.array([1,0],dtype='<f4').tobytes()))
            data = [('unrelated','Cancer therapy','Asthma may coexist.','# Treatment',[1,0]),
                    ('valid','Asthma guideline','Asthma control and follow-up.','# Treatment',[0,1]),
                    ('references','Asthma reference list','Asthma citation.','# References',[1,0])]
            for cid,title,body,heading,vector in data:
                path=root/(cid+'.md');path.write_text(body,encoding='utf-8')
                meta={'path':path.name,'title':title,'heading':heading,'year':'2025',
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'start':0,'end':1}
                db.execute('insert into chunks values(?,?,?)',(cid,json.dumps(meta),np.array(vector,dtype='<f4').tobytes()))
            db.commit();db.close()
            store=VectorStore(root/'index.db',root)
            result=store.search('asthma')
            self.assertEqual([r['chunk_id'] for r in result],['valid'])
            self.assertEqual(result,store.search('asthma'))
            store.fts=False
            self.assertEqual([r['chunk_id'] for r in store.search('asthma')],['valid'])
            (root/'valid.md').write_text('Changed evidence.',encoding='utf-8')
            self.assertEqual(store.search('asthma'),[])
            self.assertEqual(store.search('disease management'),[])
            store.close()
