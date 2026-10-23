import csv
from pathlib import Path
import tempfile
import unittest
from nova_agent.guidelines import Guidelines


class GuidelineRetrievalTests(unittest.TestCase):
    def corpus(self,root,filename='KR_Test/source.md'):
        (root/'KR_Test').mkdir()
        (root/'KR_Test/source.md').write_text('제목과 출처\n'+'문서 정보\n'*16+'개발용 근거 원문입니다.\n')
        keys=['제목','발행기관','문서 유형','파일명','연도','언어','라이선스','출처 URL']
        with (root/'catalog.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
            w.writerow(dict(zip(keys,['개발용 근거','시험기관','진료지침',filename,'2026','ko','test','https://example.org/source'])))

    def test_returns_original_source_and_provenance_without_modifying_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.corpus(root)
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=Guidelines(root).search('개발용',limit=1)
            self.assertTrue(result['available']);doc=result['documents'][0]
            self.assertEqual(doc['source_url'],'https://example.org/source');self.assertEqual(doc['license'],'test')
            self.assertTrue(doc['excerpt_only']);self.assertTrue(doc['sha256'])
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_absent_resource_is_an_explicit_optional_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(Guidelines(d).search('개발용')['available'])

    def test_catalog_cannot_read_outside_resource_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.corpus(root,'../outside.md')
            with self.assertRaises(ValueError):Guidelines(root).search('개발용')


if __name__=='__main__':unittest.main()
