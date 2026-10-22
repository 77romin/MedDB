"""authoring/followups.txt → meddb/data/followups.json (양성 소견 뒤 구체화 질문). 표준 라이브러리만.

    python tools/compile_followups.py authoring meddb/data
검사: 질문 30자 이내·물음표 하나, 참조하는 소견·슬롯이 KB 에 있어야 함.
"""
import json
import sys
import unicodedata
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
ids = {r["id"] for r in json.loads((out / "findings.json").read_text(encoding="utf-8"))}
ids |= {r["id"] for r in json.loads((out / "slots.json").read_text(encoding="utf-8"))}
data, errors = {}, []
for n, line in enumerate((src / "followups.txt").read_text(encoding="utf-8").splitlines(), 1):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    key, _, rest = line.partition(":")
    key = key.strip()
    qs = [unicodedata.normalize("NFC", q.strip()) for q in rest.split(";") if q.strip()]
    if key not in ids:
        errors.append(f"{n}행: {key} 는 KB 소견·슬롯이 아님")
    for q in qs:
        if len(q) > 30 or q.count("?") != 1 or not q.endswith("?"):
            errors.append(f"{n}행: 질문 형식 오류 '{q}'")
    data[key] = qs
if errors:
    sys.exit("\n".join(errors))
(out / "followups.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"followups: {len(data)}개 소견, 질문 {sum(len(v) for v in data.values())}개")
