#!/usr/bin/env python3
"""대회 진료지침 코퍼스의 목록(catalog.csv)에서 KB의 주호소·질환에 해당하는 문서를 골라
meddb/data/ext_guidelines.json을 만든다 (표준 라이브러리만).

    python tools/map_guidelines.py --catalog <catalog.csv>

가져오는 것은 목록에 있는 서지 정보(파일명, 제목, 발행기관, 연도, 언어, 유형, 라이선스)뿐이고
문서 본문은 읽지도 옮기지도 않는다. 본문은 실행 환경의 NOVA_GUIDELINES_DIR 에서 읽는다.
제목만 보고 고르므로 본문이 실제로 맞는지는 확인되지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "meddb" / "data"
PER_ITEM = 4
# 진료 중 참고하기 좋은 순서: 한국어 증상·질환 설명, 교과서형 개요, 국내 지침, 그 밖의 지침
FOLDER_RANK = {"KR_HealthInfo": 0, "US_StatPearls": 1, "KR_Societies": 2, "KR_Journals": 2, "KR_KDCA": 2,
               "KR_KoMGI": 2, "KR_NECA": 2, "KR_NCC": 2, "KR_EuropePMC": 3}


def has_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", s))


def matcher(term: str):
    term = term.lower().strip()
    if has_hangul(term):
        # 띄어쓰기를 지우고 비교하면 "부정맥"이 "심부 정맥 혈전증"에 걸리므로, 부분 일치는 원문 그대로 본다.
        # 두 글자 말("장염", "게실")은 다른 병명 안에 흔히 들어 있어 제목 전체가 같을 때만 인정한다.
        compact = term.replace(" ", "")
        if len(compact) <= 2:
            return lambda title: title.replace(" ", "") == compact
        return lambda title: term in title or title.replace(" ", "") == compact
    pattern = re.compile(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])")
    return lambda title: bool(pattern.search(title))


def clean(title: str) -> str:
    return re.sub(r"\s*\(archived\)\s*$", "", title.lower()).strip()


def pick(rows: list[dict], terms: list[str], exclude: list[str]) -> list[dict]:
    rows = [r for r in rows if not any(x.lower() in r["_title"] for x in exclude)]
    scored = []
    for order, term in enumerate(terms):
        match = matcher(term)
        key = term.lower().strip()
        for r in rows:
            title = r["_title"]
            if not match(title):
                continue
            base = clean(title)
            exact = 0 if base == key or base.replace(" ", "") == key.replace(" ", "") else 1
            archived = int("(archived)" in title)
            folder = FOLDER_RANK.get(r["_folder"], 4)
            year = -int(r["연도"]) if r["연도"].isdigit() else 0
            scored.append(((exact, archived, folder, order, len(title), year), r))
    out, seen = [], set()
    for _score, r in sorted(scored, key=lambda x: x[0]):
        if r["파일명"] in seen:
            continue
        seen.add(r["파일명"])
        out.append({"file": r["파일명"], "title": r["제목"], "org": r["발행기관"], "year": r["연도"],
                    "lang": {"한국어": "ko", "영어": "en"}.get(r["언어"], r["언어"]), "type": r["문서 유형"],
                    "license": r["라이선스"]})
        if len(out) >= PER_ITEM:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    args = ap.parse_args()
    rows = list(csv.DictReader(io.StringIO(Path(args.catalog).read_bytes().decode("utf-8-sig"))))
    for r in rows:
        r["_title"] = r["제목"].lower()
        r["_folder"] = r["파일명"].split("/")[0]
    extra = json.loads((ROOT / "tools" / "guideline_terms.json").read_text(encoding="utf-8"))
    diseases = json.loads((DATA / "diseases.json").read_text(encoding="utf-8"))
    complaints = json.loads((DATA / "complaints.json").read_text(encoding="utf-8"))

    def terms(item: dict, kind: str) -> list[str]:
        own = [item["ko"]] + ([item["en"]] if item.get("en") else [])
        own += [a for a in item.get("alias", []) if kind == "disease" and len(a) >= 3 and not a.isupper()]
        out: list[str] = []
        for t in own + extra[kind].get(item["id"], []):
            if t.lower() not in [o.lower() for o in out]:
                out.append(t)
        return out

    def skip(item_id: str) -> list[str]:
        return extra["exclude"].get("_all", []) + extra["exclude"].get(item_id, [])

    result = {"diseases": {}, "complaints": {}}
    for d in diseases:
        result["diseases"][d["id"]] = pick(rows, terms(d, "disease"), skip(d["id"]))
    for c in complaints:
        result["complaints"][c["id"]] = pick(rows, terms(c, "complaint"), skip(c["id"]))
    used = {doc["file"] for group in result.values() for docs in group.values() for doc in docs}
    meta = {
        "source": "N.O.V.A. 2026 진료지침 코퍼스 catalog.csv",
        "note": "서지 정보만 담음. 제목 일치로 고른 것이라 본문 적합성은 확인되지 않음. 문서를 쓸 때 라이선스와 출처를 함께 표시할 것.",
        "catalog_documents": len(rows), "documents_linked": len(used),
        "diseases_with_documents": sum(bool(v) for v in result["diseases"].values()),
        "complaints_with_documents": sum(bool(v) for v in result["complaints"].values()),
    }
    lines = ['{', '  "meta": ' + json.dumps(meta, ensure_ascii=False) + ","]
    for gi, group in enumerate(("complaints", "diseases")):
        lines.append(f'  "{group}": {{')
        items = list(result[group].items())
        for i, (key, docs) in enumerate(items):
            body = ",\n".join("      " + json.dumps(doc, ensure_ascii=False) for doc in docs)
            tail = "," if i < len(items) - 1 else ""
            lines.append(f'    "{key}": [\n{body}\n    ]{tail}' if docs else f'    "{key}": []{tail}')
        lines.append("  }" + ("," if gi == 0 else ""))
    lines.append("}")
    (DATA / "ext_guidelines.json").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(meta)
    for group in ("complaints", "diseases"):
        empty = [k for k, v in result[group].items() if not v]
        print(group, "문서 없음:", empty)


if __name__ == "__main__":
    main()
