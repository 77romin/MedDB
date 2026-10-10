import gzip
import json
import tempfile
import unittest
from pathlib import Path
from meddb.kcd import KCD

class KCDTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / 'fixture.json.gz'
        rows = [dict(code='A123', label_ko='시험 이름', label_en='Test name', source_row=12),
                dict(code='A123', label_ko='다른 시험 이름', label_en='Other test name', source_row=13),
                dict(code='B001', label_ko='세 번째 이름', label_en='Third name', source_row=14)]
        path.write_bytes(gzip.compress(json.dumps(dict(records=rows, code_system='KCD-9', source_version='fixture', source_sha256='fixture')).encode()))
        self.kcd = KCD(path)

    def test_code_preserves_multiple_names_and_dotted_query(self):
        result = self.kcd.code('A12.3')
        self.assertEqual(len(result['names']), 2)
        self.assertEqual(self.kcd.search('A12.3')['total'], 2)

    def test_pagination_and_invalid_limits(self):
        result = self.kcd.search('', 1, 1)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['rows'][0]['source_row'], 13)
        for limit in [0, 101]:
            with self.assertRaises(ValueError): self.kcd.search(limit=limit)

    def test_name_candidate_is_draft_and_not_fuzzy(self):
        result = self.kcd.candidates(dict(id='test:disease', label_ko='시험 이름', label_en=' Test   NAME ', aliases=[]))
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(result['review_status'], 'draft')
        result = self.kcd.candidates(dict(id='test:disease', label_ko='시험', label_en='Test', aliases=[]))
        self.assertEqual(result['candidates'], [])
