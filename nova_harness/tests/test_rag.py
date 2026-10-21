import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from nova_agent.rag import chunks


class ChunkTests(unittest.TestCase):
    def test_provenance_and_no_loss(self):
        text = '---\ntitle: a\n---\n# Recommendation\nKeep treatment.\n## Exception\nAvoid in pregnancy.\n'
        parts = list(chunks(text, 45))
        lines = text.splitlines(keepends=True)
        self.assertEqual(''.join(p[3] for p in parts), ''.join(lines[3:]))
        for start, end, _, body in parts:
            self.assertEqual(body, ''.join(lines[start:end]))

    def test_short_exception_is_preserved(self):
        text = '# Advice\nUse therapy.\n## Exception\nAvoid in pregnancy.\n'
        self.assertIn('Avoid in pregnancy.', ''.join(p[3] for p in chunks(text)))


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'R1 optional numpy dependency')
class VectorTests(unittest.TestCase):
    def test_query_projection_source_hash_oov_and_readonly(self):
        import numpy as np
        from nova_agent.rag import VectorStore
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'a.md'
            source.write_text('Asthma evidence.\n', encoding='utf-8')
            db = sqlite3.connect(root/'index.db')
            db.executescript('create table meta(key,value);create table terms(id,token,idf,projection);'
                             'create table chunks(id,metadata,vector);')
            db.execute('insert into meta values(?,?)', ('dimensions','2'))
            db.execute('insert into terms values(?,?,?,?)', (0,'asthma',1.,np.array([1,0],dtype='<f4').tobytes()))
            meta = {'path':'a.md','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'start':0,'end':1}
            db.execute('insert into chunks values(?,?,?)', ('a',json.dumps(meta),np.array([1,0],dtype='<f4').tobytes()))
            db.commit(); db.close()
            store = VectorStore(root/'index.db', root)
            self.assertEqual(store.search('asthma')[0]['excerpt'], source.read_text())
            self.assertEqual(store.search('zzzz'), [])
            source.write_text('Changed evidence.', encoding='utf-8')
            self.assertEqual(store.search('asthma'), [])
            with self.assertRaises(sqlite3.OperationalError):
                store.db.execute('delete from chunks')
            store.close()

    def test_overlay_injects_record_only_and_restores(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from nova_agent.e2_rag import install, restore
        calls = []
        class Client:
            def chat(self, messages, **kw):
                calls.append(messages)
                return 'response'
        def original(client, *args):
            return client.chat([{'role':'system','content':'record'}], max_tokens=10)
        h = SimpleNamespace(write_record=original)
        modules = {'examples':SimpleNamespace(hybrid_agent=h)}
        kb = SimpleNamespace(complaint='a',ranked=lambda k: [{'id':'a'}])
        db = SimpleNamespace(diseases={'a':{'ko':'질환','en':'condition'}})
        store = SimpleNamespace(search=lambda *a, **kw: [{'chunk_id':'e1','excerpt':'reference'}])
        with patch.dict(sys.modules, modules):
            old = install(store)
            try:
                self.assertEqual(h.write_record(Client(),db,kb,'opening',{},[]), 'response')
                self.assertIn('환자 관찰 아님', calls[0][-1]['content'])
            finally:
                restore(old)
            self.assertIs(h.write_record, original)

    def test_no_evidence_preserves_original_client_and_inputs(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from nova_agent.e2_rag import install, restore
        client = object()
        kb = SimpleNamespace(complaint='a', ranked=lambda k: [{'id':'a'}])
        db = SimpleNamespace(diseases={'a':{'en':'asthma'}})
        received = []
        def original(*args):
            received.append(args)
            return ('unchanged', 'diagnosis')
        h = SimpleNamespace(write_record=original)
        with patch.dict(sys.modules, {'examples':SimpleNamespace(hybrid_agent=h)}):
            old = install(SimpleNamespace(search=lambda *a, **kw: []))
            try:
                result = h.write_record(client,db,kb,'initial',{},[],True)
            finally:
                restore(old)
        self.assertEqual(result, ('unchanged','diagnosis'))
        self.assertIs(received[0][0], client)
        self.assertTrue(received[0][-1])
