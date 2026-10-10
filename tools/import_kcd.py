"""Extract the official HIRA workbook without collapsing different names per code.

Requires openpyxl for read-only extraction. Does not assert disease equivalence.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

COLUMNS = ['code', 'label_ko', 'label_en', 'complete_code_flag', 'primary_diagnosis_flag',
           'infectious_disease_class', 'sex_flag', 'upper_age', 'lower_age', 'medicine_type']
HEADERS = ['상병기호', '한글명', '영문명', '완전코드구분', '주상병사용구분',
           '법정감염병구분', '성별구분', '상한연령', '하한연령', '양•한방구분']

def extract(path):
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book['상병분류기호(전체)']
    rows, codes, header_found = [], {}, False
    for number, row in enumerate(sheet.iter_rows(values_only=True), 1):
        values = list(row[1:11])
        if not header_found:
            if values == HEADERS:
                header_found = True
            continue
        if not values[0]:
            continue
        if not isinstance(values[0], str) or not isinstance(values[1], str):
            raise ValueError(f'Unexpected code/name at row {number}')
        record = dict(zip(COLUMNS, values), source_row=number)
        record['code'] = record['code'].strip()
        rows.append(record)
        codes.setdefault(record['code'], []).append(number)
    book.close()
    if not header_found or not rows:
        raise ValueError('HIRA workbook header or records missing')
    return {'code_system': 'KCD-9', 'source_version': 'HIRA-260329',
            'sheet': sheet.title, 'records': rows, 'code_rows': codes,
            'semantics': 'Names and claim flags preserved per source row; no disease mapping or clinical inference'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; use a new snapshot path')
    result = extract(args.workbook)
    result['source_sha256'] = hashlib.sha256(args.workbook.read_bytes()).hexdigest()
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(payload, mtime=0))
    print(json.dumps({'records': len(result['records']), 'unique_codes': len(result['code_rows']),
                      'source_sha256': result['source_sha256']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
