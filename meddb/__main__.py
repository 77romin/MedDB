"""python -m meddb validate | build [경로] | stats | demo "환자 첫마디" | kcd-check <상병마스터 파일>"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .api import MedDB
from .build import build_file, load_sources, validate


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "validate"
    if cmd == "validate":
        errors, warnings = validate(load_sources())
        for w in warnings:
            print("경고", w)
        for e in errors:
            print("오류", e)
        print(f"오류 {len(errors)}건, 경고 {len(warnings)}건")
        return 1 if errors else 0
    if cmd == "build":
        path = build_file(argv[1] if len(argv) > 1 else "dist/meddb.sqlite")
        print(f"{path} ({path.stat().st_size / 1024:.0f} KB)")
        return 0
    if cmd == "stats":
        db = MedDB.open()
        print(json.dumps({"complaints": len(db.complaints), "diseases": len(db.diseases),
                          "red_flag_diseases": sum(d["red_flag"] for d in db.diseases.values()),
                          "findings": len(db.findings), "exams": len(db.exams), "slots": len(db.slots),
                          "disease_finding_links": sum(len(r) for r in db.roles.values())}, ensure_ascii=False))
        return 0
    if cmd == "demo":
        db = MedDB.open()
        text = argv[1] if len(argv) > 1 else "가슴이 너무 아파서 왔어요."
        hits = db.match_complaint(text)
        print("주호소:", [h["ko"] for h in hits] or "찾지 못함")
        if hits:
            cid = hits[0]["id"]
            for a in db.next_actions(cid, limit=8):
                print(f"  [{a['stage']:<12}] {a['type']:<4} {a['text']}  ({a['why']})")
            print("후보:", [(c["ko"], c["score"]) for c in db.candidates(cid)])
        return 0
    if cmd == "kcd-check" and len(argv) > 1:
        # 상병마스터(CSV/TSV, 공공데이터포털)에서 코드 꼴의 문자열을 모두 모아 KB의 KCD 코드와 대조한다.
        raw = Path(argv[1]).read_bytes()
        text = raw.decode("utf-8", errors="ignore") + raw.decode("cp949", errors="ignore")
        master = {m.replace(".", "") for m in re.findall(r"\b[A-Z]\d{2}\.?\d{0,2}\b", text)}
        db = MedDB.open()
        missing = [(d["id"], d["kcd"]) for d in db.diseases.values()
                   if d["kcd"] and d["kcd"].replace(".", "") not in master]
        for did, code in missing:
            print("상병마스터에 없음", did, code)
        print(f"KCD 코드 {sum(1 for d in db.diseases.values() if d['kcd'])}개 중 {len(missing)}개 불일치")
        return 1 if missing else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
