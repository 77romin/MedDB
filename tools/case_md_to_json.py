"""대회 공개 샘플의 case.md 를 로컬 실행용 증례 JSON 으로 바꾼다 (표준 라이브러리만).

    python tools/case_md_to_json.py C01\\case.md --id C01 --answer "수면제 의존" -o local/cases/samples/C01.json

case.md 구성: '시작 정보'(인용문 opening + 활력징후), '가상 환자 대본', '진찰 결과표'.
대본은 문장 단위로 잘라 facts 로 넣는다(가상 환자 역할의 로컬 모델이 근거로 씀).
공개 샘플 원문이 들어가므로 만든 JSON 은 git 에 올리지 않는다(.gitignore).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def sections(text):
    parts, name = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            name = m.group(1)
            parts[name] = []
        elif name:
            parts[name].append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def pick(parts, word):
    for k, v in parts.items():
        if word in k:
            return v
    raise SystemExit(f"case.md 에 '{word}' 섹션이 없습니다")


def find_diagnosis(folder):
    """같은 폴더의 model_record.json / model_record.md 에서 모범 주진단을 찾는다."""
    js = Path(folder) / "model_record.json"
    if js.exists():
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if "diagnos" in k.lower() and isinstance(x, str) and x.strip():
                        return x.strip()
                for x in v.values():
                    r = walk(x)
                    if r:
                        return r
            elif isinstance(v, list):
                for x in v:
                    r = walk(x)
                    if r:
                        return r
            return None
        r = walk(json.loads(js.read_text(encoding="utf-8-sig")))
        if r:
            return r
    md = Path(folder) / "model_record.md"
    if md.exists():
        lines = md.read_text(encoding="utf-8-sig").splitlines()
        for i, line in enumerate(lines):
            if re.search(r"주\s*진단|최종\s*진단|Diagnosis", line, re.I):
                rest = re.split(r"[:：]", line, maxsplit=1)
                if len(rest) == 2 and rest[1].strip(" *#|"):
                    return rest[1].strip(" *#|")
                for nxt in lines[i + 1:i + 6]:
                    if nxt.strip().startswith("```"):
                        continue
                    if nxt.strip(" -*#|>"):
                        return nxt.strip(" -*#|>")
    return ""


def convert(path, case_id=None, answer=""):
    text = Path(path).read_text(encoding="utf-8-sig")
    parts = sections(text)
    start = pick(parts, "시작 정보")
    opening = " ".join(l.lstrip("> ").strip() for l in start.splitlines() if l.startswith(">")).strip()
    vitals = [l.strip() for l in start.splitlines() if l.strip() and not l.startswith(">")]
    vital_signs = "\n".join(v.rstrip() for v in vitals)

    script = pick(parts, "가상 환자")
    paragraphs = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", script) if p.strip()]
    if paragraphs and paragraphs[0].replace(" ", "") == opening.replace(" ", ""):
        paragraphs = paragraphs[1:]  # 첫 문단은 opening 과 같다
    facts = []
    for p in paragraphs:
        facts += [s.strip() for s in re.split(r"(?<=[.?!])\s+", p) if s.strip()]

    exams = {}
    for line in pick(parts, "진찰 결과표").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("진찰", "") and not set(cells[0]) <= set("-: "):
            exams[cells[0]] = cells[1]

    answer = find_diagnosis(Path(path).parent) or answer
    title = re.search(r"^#\s+(.+)$", text, re.M)
    cid = case_id or (title.group(1).split()[-1] if title else Path(path).stem)
    return {"id": cid, "_source": f"대회 공개 샘플 {cid} case.md 변환 (로컬 시험 전용, 재배포 금지)",
            "opening": opening, "vital_signs": vital_signs, "facts": facts, "exams": exams,
            "default_exam": "특이 소견 없음", "answer": {"diagnosis": answer or "(모범 기록 미첨부)"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_md")
    ap.add_argument("--id")
    ap.add_argument("--answer", default="")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    case = convert(args.case_md, args.id, args.answer)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}  opening {len(case['opening'])}자 · facts {len(case['facts'])} · exams {len(case['exams'])}")


if __name__ == "__main__":
    main()
