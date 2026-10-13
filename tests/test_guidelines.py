import csv
from pathlib import Path
import tempfile
import unittest
from meddb.guidelines import Guidelines


class GuidelineTests(unittest.TestCase):
    def test_unavailable_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=Guidelines(tmp)
            self.assertFalse(g.search('insomnia')['available'])

    def test_source_license_and_exact_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);text='---\ntitle: Insomnia\nlicense: CC BY-NC-ND\n---\n\nOriginal insomnia source text.\n'
            (root/'source.md').write_text(text,encoding='utf-8')
            with (root/'catalog.csv').open('w',encoding='utf-8-sig',newline='') as f:
                fields=['파일명','제목','발행기관','연도','언어','문서 유형','라이선스','출처 URL'];writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerow(dict(zip(fields,['source.md','Insomnia','Test institution','2026','영어','진료지침','CC BY-NC-ND','https://example.org/source'])))
            result=Guidelines(root).search('insomnia')
            doc=result['documents'][0]
            self.assertEqual(doc['license'],'CC BY-NC-ND')
            self.assertIn(doc['excerpt'],text)
            self.assertEqual((root/'source.md').read_text(encoding='utf-8'),text)

    def test_path_traversal_in_catalog_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with (root/'catalog.csv').open('w',encoding='utf-8',newline='') as f:
                fields=['파일명','제목','발행기관','연도','언어','문서 유형','라이선스','출처 URL'];writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerow(dict(zip(fields,['../secret.md','Insomnia','Test','2026','영어','진료지침','CC BY','https://example.org'])))
            with self.assertRaises(ValueError):Guidelines(root).search('insomnia')
