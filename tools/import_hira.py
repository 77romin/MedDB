#!/usr/bin/env python3
"""건강보험심사평가원 공개 파일 두 개를 KB용 압축 표로 바꾼다 (표준 라이브러리만).

    python tools/import_hira.py --kcd <상병마스터.csv> --stats <주부상병(3단) 성별 연령군별 진료 통계.csv>

출력 (meddb/data/):
  kcd.tsv.gz        코드, 한글명, 영문명, 대표 여부(1=그 코드의 첫 줄, 0=포함 용어)
  hira_prev.tsv.gz  KCD 3자리 코드, 성별(M/F), 연령군 번호(1~18, 5세 단위), 환자수
원본은 공공데이터포털에서 받는다 (공공누리 제1유형, 출처: 건강보험심사평가원). docs/SOURCES.md 참고.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "meddb" / "data"


def read_csv(path: str) -> list[dict]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return list(csv.DictReader(io.StringIO(raw.decode(enc))))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"인코딩을 알 수 없음: {path}")


def write_gz(name: str, rows: list[tuple]) -> None:
    # mtime=0: 같은 입력이면 같은 바이트가 나오도록
    with open(OUT / name, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write("".join("\t".join(str(c) for c in row) + "\n" for row in rows).encode("utf-8"))
    print(name, len(rows), "행", f"{(OUT / name).stat().st_size / 1024:.0f} KB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kcd")
    ap.add_argument("--stats")
    args = ap.parse_args()
    if args.kcd:
        seen: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        rows = []
        for r in read_csv(args.kcd):
            code, ko, en = r["상병기호"].strip(), r["한글명"].strip(), r["영문명"].strip()
            if not code or not ko or (code, ko) in pairs:
                continue
            pairs.add((code, ko))
            rows.append((code, ko.replace("\t", " "), en.replace("\t", " "), int(code not in seen)))
            seen.add(code)
        write_gz("kcd.tsv.gz", rows)
    if args.stats:
        rows = []
        for r in read_csv(args.stats):
            sex = {"남": "M", "여": "F"}[r["성별"].strip()]
            rows.append((r["상병코드"].strip(), sex, int(r["연령군"].split("_")[0]), int(r["환자수"])))
        write_gz("hira_prev.tsv.gz", rows)


if __name__ == "__main__":
    main()
