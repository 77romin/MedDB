"""authoring/protocols.txt → meddb/data/protocols.json (주호소별 표준 문진·진찰 프로토콜, E10).

검사: 질문 30자 이내·물음표 하나·'~나/~거나' 묶음 질문 경고, 소견·진찰·주호소 id 존재, 기록칸 이름, 조건 형식.
    python tools/compile_protocols.py            # 컴파일 (문제 있으면 실패)
    python tools/compile_protocols.py --check    # 검사만
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "authoring" / "protocols.txt"
OUT = ROOT / "meddb" / "data" / "protocols.json"
FIELDS = {"hpi", "pmh", "fh", "sh", "ros"}
COND = re.compile(r"^(sex=[FM]|age>=\d+|age<\d+|age=\d+-\d+)$")
MAX = 30


def _nfc(s):
    return unicodedata.normalize("NFC", s.strip())


def _cond(text, where, errors):
    out = {}
    for tok in text.split():
        if not COND.match(tok):
            errors.append(f"{where}: 조건 형식 '{tok}'")
            continue
        if tok.startswith("sex="):
            out["sex"] = tok[4:]
        elif tok.startswith("age>="):
            out["age_min"] = int(tok[5:])
        elif tok.startswith("age<"):
            out["age_max"] = int(tok[4:]) - 1
        else:
            lo, hi = tok[4:].split("-")
            out["age_min"], out["age_max"] = int(lo), int(hi)
    return out


def compile_protocols():
    data = {n: json.loads((ROOT / "meddb" / "data" / f"{n}.json").read_text(encoding="utf-8"))
            for n in ("findings", "exams", "complaints")}
    def ids(rows):
        return set(rows) if isinstance(rows, dict) else {r["id"] for r in rows}
    findings, exams, complaints = ids(data["findings"]), ids(data["exams"]), ids(data["complaints"])
    out = {"exams": {}, "complaints": {}}
    errors, warnings, block = [], [], None
    for n, raw in enumerate(SRC.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line == "#" or (line.startswith("#") and " " in line):
            continue                                   # 빈 줄·설명 주석
        where = f"{SRC.name}:{n}"
        if line == "@exams":
            block = "@exams"
            continue
        if line.startswith("#"):
            block = line[1:]
            if block != "default" and block not in complaints:
                errors.append(f"{where}: 주호소 id '{block}' 없음")
            out["complaints"][block] = {"items": [], "exams": [], "family": True}
            continue
        key, _, rest = line.partition(":")
        parts = [_nfc(p) for p in rest.split("|")]
        if block == "@exams":
            if key != "x" or len(parts) != 3:
                errors.append(f"{where}: @exams 는 'x: id | 진찰명 | 행동 문장'")
                continue
            eid, ko, action = parts
            if len(action) > MAX:
                errors.append(f"{where}: 행동 문장 {len(action)}자 > {MAX}")
            out["exams"][eid] = {"id": eid, "ko": ko, "action": action}
            continue
        if block is None:
            errors.append(f"{where}: 주호소(#id) 전에 항목이 있음")
            continue
        proto = out["complaints"][block]
        if key == "family":
            proto["family"] = parts[0] != "no"
        elif key == "s":
            if len(parts[0]) > MAX or not re.search(r"(오세요|부르세요)\.?$", parts[0]):
                errors.append(f"{where}: 위험 신호 문장은 30자 이내, '오세요/부르세요'로 끝남: {parts[0]}")
            proto["safety"] = parts[0]
        elif key == "q":
            if len(parts) < 3:
                errors.append(f"{where}: 'q: id | 질문 | 기록칸 | 조건'")
                continue
            qid, text, field = parts[:3]
            cond = _cond(parts[3], where, errors) if len(parts) > 3 else {}
            if len(text) > MAX:
                errors.append(f"{where}: 질문 {len(text)}자 > {MAX}: {text}")
            if text.count("?") != 1 or not text.endswith("?"):
                errors.append(f"{where}: 물음표 하나로 끝나야 함: {text}")
            if field not in FIELDS:
                errors.append(f"{where}: 기록칸 '{field}'")
            if re.search(r"(거나|이나) ", text):
                warnings.append(f"{where}: 묶음 질문일 수 있음(환자가 '하나씩'이라 답할 수 있음): {text}")
            proto["items"].append(dict({"kind": "q", "id": "pr_" + qid, "text": text, "field": field}, **cond))
        elif key == "f":
            fid = parts[0]
            cond = _cond(parts[1], where, errors) if len(parts) > 1 else {}
            if fid not in findings:
                errors.append(f"{where}: 소견 id '{fid}' 없음")
            proto["items"].append(dict({"kind": "f", "id": fid}, **cond))
        elif key == "x":
            eid = parts[0]
            cond = _cond(parts[1], where, errors) if len(parts) > 1 else {}
            if eid not in exams and eid not in out["exams"]:
                errors.append(f"{where}: 진찰 id '{eid}' 없음 (@exams 에 등록)")
            proto["exams"].append(dict({"id": eid}, **cond))
        else:
            errors.append(f"{where}: 알 수 없는 줄 '{line}'")
    seen = {}
    for cid, proto in out["complaints"].items():
        for it in proto["items"]:
            if it["kind"] == "q":
                if it["id"] in seen and seen[it["id"]] != it["text"]:
                    errors.append(f"{cid}: 같은 id 다른 질문 {it['id']}")
                seen[it["id"]] = it["text"]
    return out, errors, warnings


def main():
    out, errors, warnings = compile_protocols()
    for w in warnings:
        print("경고:", w)
    if errors:
        for e in errors:
            print("오류:", e)
        sys.exit(1)
    n_q = sum(len(p["items"]) for p in out["complaints"].values())
    n_x = sum(len(p["exams"]) for p in out["complaints"].values())
    print(f"주호소 {len(out['complaints'])}개, 문진 {n_q}개, 진찰 {n_x}개, 새 진찰 {len(out['exams'])}개")
    if "--check" not in sys.argv:
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("→", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
