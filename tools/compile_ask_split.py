"""authoring/ask_split.txt → meddb/data/ask_split.json (묶음 질문을 한 가지씩 나눈 질문). 표준 라이브러리만.

    python tools/compile_ask_split.py
검사: id 가 소견·슬롯에 있음, 원래 질문이 묶음 꼴(거나/이나), 나눈 질문은 30자 이내·물음표 하나.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "meddb" / "data"
rows = {r["id"]: r for n in ("findings", "slots") for r in json.loads((DATA / f"{n}.json").read_text(encoding="utf-8"))}
out, errors = {}, []
for n, line in enumerate((ROOT / "authoring" / "ask_split.txt").read_text(encoding="utf-8").splitlines(), 1):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = [unicodedata.normalize("NFC", p.strip()) for p in line.split("|")]
    if len(parts) != 3:
        errors.append(f"{n}: 'id | 질문1 | 질문2'")
        continue
    fid, a, b = parts
    if fid not in rows:
        errors.append(f"{n}: id '{fid}' 없음")
        continue
    if not re.search(r"(거나|이나|나) ", rows[fid].get("ask") or ""):
        errors.append(f"{n}: '{fid}' 원래 질문이 묶음 꼴이 아님: {rows[fid].get('ask')}")
    for q in (a, b):
        if len(q) > 30 or q.count("?") != 1 or not q.endswith("?"):
            errors.append(f"{n}: 질문 형식 '{q}'")
    out[fid] = [a, b]
missing = [k for k, r in rows.items() if re.search(r"(거나|이나) ", r.get("ask") or "") and k not in out]
if missing:
    errors.append("나누기 없는 묶음 질문: " + ", ".join(missing))
if errors:
    print("\n".join("오류: " + e for e in errors))
    sys.exit(1)
(DATA / "ask_split.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"묶음 질문 {len(out)}개 → meddb/data/ask_split.json")
