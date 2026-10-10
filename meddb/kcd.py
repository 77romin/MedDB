"""Local HIRA KCD-9 code lookup, separate from clinical disease concepts."""
import gzip
import json
import re
from pathlib import Path

DEFAULT_KCD = Path(__file__).resolve().parents[1] / 'data/terminology/kcd/hira-kcd9-260329.json.gz'

def name_key(value):
    return re.sub(r'\s+', ' ', value.replace('’', "'").strip()).casefold()

class KCD:
    def __init__(self, path=DEFAULT_KCD):
        self.data = json.loads(gzip.decompress(Path(path).read_bytes()))
        self.rows = self.data['records']
        self.by_code = {}
        self.by_name = {}
        for row in self.rows:
            self.by_code.setdefault(row['code'], []).append(row)
            for key in {name_key(row['label_ko'] or ''), name_key(row['label_en'] or '')} - {''}:
                self.by_name.setdefault(key, []).append(row)

    def metadata(self):
        return dict(code_system=self.data['code_system'], version=self.data['source_version'],
                    sha256=self.data['source_sha256'], rows=len(self.rows), codes=len(self.by_code),
                    includes_activity_codes=True, source_url='https://www.hira.or.kr/rc/drug/insuadtcrtr/bbsView.do?brdBltNo=53117&brdScnBltNo=4&pgmid=HIRAA030069000400')

    def search(self, query='', offset=0, limit=50):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid KCD pagination')
        q = name_key(query)
        code = query.strip().upper().replace('.', '')
        rows = self.rows if not q else [r for r in self.rows if
               code in r['code'] or q in name_key(r['label_ko'] or '') or q in name_key(r['label_en'] or '')]
        return dict(metadata=self.metadata(), total=len(rows), offset=offset, rows=rows[offset:offset+limit])

    def code(self, value):
        value = value.strip().upper().replace('.', '')
        if value not in self.by_code:
            raise ValueError('Unknown KCD code')
        return dict(metadata=self.metadata(), code=value, names=self.by_code[value],
                    note='One classification code can contain multiple disease names. No exact disease equivalence is asserted.')

    def candidates(self, concept):
        matches = {}
        for name in [concept['label_ko'], concept['label_en'], *concept.get('aliases', [])]:
            for row in self.by_name.get(name_key(name), []):
                matches[row['source_row']] = dict(**row, matched_name=name)
        return dict(metadata=self.metadata(), concept_id=concept['id'], candidates=list(matches.values()),
                    method='normalized_exact_name', review_status='draft',
                    note='Name matches are review candidates, not approved code mappings.')
