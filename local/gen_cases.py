"""검증용 가상 증례를 로컬 Ollama(gpt-oss:20b)로 만든다. 공개 샘플(case.md)과 같은 형식으로 쓴다.

    python local/gen_cases.py                    # local/dev_specs.json 의 30건 모두 (이미 만든 건 건너뜀)
    python local/gen_cases.py --ids D01 D02      # 일부만
    python local/gen_cases.py --force            # 다시 만들기

결과: dev_cases/<ID>/case.md, dev_cases/<ID>/model_record.md (주진단만).
증례 내용은 모델이 쓰고, 이 스크립트는 형식만 알려 준다. 진찰 이름 목록은 공개 샘플 진찰표의 표준명 체계를 따른다.
KB를 만든 사람이 증례를 직접 쓰면 KB에 유리한 증례가 되기 쉬워서 이렇게 분리했다.
만든 증례는 사람이 한 번 훑어보고 이상한 것(진단과 안 맞는 대본, 정답을 말해 버리는 대본)은 지우거나 다시 만든다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
from case_md_to_json import convert  # noqa: E402

OLLAMA = "http://localhost:11434/v1/chat/completions"
MODEL = "gpt-oss:20b"

COMMON_EXAMS = [
    "전반적 외관 시진 (General appearance)", "의식·지남력 평가 (Mental status)", "활력징후 측정 (Vital signs)",
    "결막·공막 시진 (Conjunctiva and sclera inspection)", "경부 림프절 촉진 (Cervical lymph node palpation)",
    "갑상선 촉진 (Thyroid palpation)", "흉곽 시진 (Chest inspection)", "폐 청진 (Lung auscultation)",
    "심음 청진 (Heart auscultation)", "복부 시진 (Abdominal inspection)", "장음 청진 (Bowel sound auscultation)",
    "복부 촉진 (Abdominal palpation)", "간·비장 촉진 (Liver and spleen palpation)",
    "하지 말초 진찰 (Peripheral pulse and edema)", "사지 근력 검사 (Limb muscle power)",
    "심부건반사 (Deep tendon reflex)", "보행 관찰 (Gait)",
]

PROMPT = """한국 의과대학 임상수행평가(CPX)용 표준화 환자 증례를 하나 작성하세요.

[증례 조건]
- 환자: {age}세 {sex}
- 내원 이유(주호소): {presentation}
- 실제 진단(정답): {diagnosis}  ← 대본과 시작 정보에는 진단명을 절대 쓰지 마세요.

[출력 형식] 아래 마크다운 형식을 정확히 지키고, 다른 말은 쓰지 마세요.

# 증례 {cid}

## 시작 정보 (Doctor Agent가 받는 내용)

> (환자의 첫마디 2~4문장. "저는 OOO이고, 마흔다섯 살 남자이다."처럼 이름과 한글로 쓴 나이·성별로 시작. 소아는 보호자와 함께 왔다고 쓴다. 진단명·검사 결과 금지)

혈압 : (수치) mmHg
맥박 : (수치) 회/분
호흡 : (수치) 회/분
체온 : (수치)°C

## 가상 환자 대본 (가상 환자만 봄)

(1인칭 서술 문단 6~9개, 30~50문장. 첫 문단은 시작 정보의 첫마디를 그대로 반복.
현병력(발생 시점, 양상, 경과, 악화·완화 요인, 동반 증상), 이 진단과 감별할 때 중요한 '없는 증상',
과거력, 복용 약, 알레르기, 가족력, 흡연·음주·직업, 환자가 걱정하는 것과 궁금한 것을 모두 포함.
진단명이나 의학 전문용어는 쓰지 않고 일반인 말투로. 소아면 보호자가 대신 답한다고 적는다.)

## 진찰 결과표 (진찰 판정 모델만 봄)

| 진찰 | 결과 |
|---|---|
(15~24행. 아래 공통 진찰 중 관련 있는 것 + 이 진단을 확인·감별하는 특수 진찰.
진찰 이름은 반드시 "한글 표준명 (English name)" 형식. 결과는 "압통(-), 종괴(-)"처럼 짧은 소견과 (+)/(-), 좌우는 (+/-).
활력징후 행의 수치는 시작 정보와 같게. 정답 진단과 맞는 양성 소견을 2~5개 넣고 나머지는 정상.)

공통 진찰 이름 목록: {exams}

## 주진단

```
{diagnosis}
```
"""


def ollama(prompt: str) -> str:
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8000, "reasoning_effort": "low", "temperature": 0.8}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["choices"][0]["message"].get("content") or ""


def check(md: str, spec: dict, out_dir: Path) -> str | None:
    """형식·내용 점검. 문제가 있으면 이유, 없으면 None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case.md").write_text(md, encoding="utf-8")
    try:
        case = convert(out_dir / "case.md", spec["id"], spec["diagnosis"])
    except SystemExit as exc:
        return str(exc)
    if not case["opening"] or len(case["facts"]) < 15:
        return f"시작 정보·대본이 짧음 (facts {len(case['facts'])})"
    if len(case["exams"]) < 10:
        return f"진찰표가 짧음 ({len(case['exams'])}행)"
    if not re.search(r"(혈압|맥박)", case["vital_signs"]):
        return "활력징후 없음"
    leak = spec["diagnosis"].replace(" ", "")
    if leak in (case["opening"] + "".join(case["facts"])).replace(" ", ""):
        return "대본에 진단명이 나옴"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=str(HERE / "dev_specs.json"))
    ap.add_argument("--out", default=str(ROOT / "dev_cases"))
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tries", type=int, default=3)
    args = ap.parse_args()
    specs = json.loads(Path(args.specs).read_text(encoding="utf-8"))["cases"]
    for spec in specs:
        if args.ids and spec["id"] not in args.ids:
            continue
        out_dir = Path(args.out) / spec["id"]
        if (out_dir / "model_record.md").exists() and not args.force:
            print(spec["id"], "이미 있음 — 건너뜀")
            continue
        prompt = PROMPT.format(cid=spec["id"], age=spec["age"], sex="남자" if spec["sex"] == "M" else "여자",
                               presentation=spec["presentation"], diagnosis=spec["diagnosis"],
                               exams=", ".join(COMMON_EXAMS))
        started = time.time()
        for attempt in range(1, args.tries + 1):
            md = ollama(prompt).strip()
            md = re.sub(r"^```(?:markdown)?\s*|\s*```\s*$", "", md) if md.startswith("```") else md
            problem = check(md, spec, out_dir)
            if problem is None:
                (out_dir / "model_record.md").write_text(
                    f"# {spec['id']} 정답\n\n## 주진단\n\n```\n{spec['diagnosis']}\n```\n", encoding="utf-8")
                print(f"{spec['id']} 완료 ({attempt}회, {time.time() - started:.0f}초) — {spec['diagnosis']}")
                break
            print(f"{spec['id']} 다시 생성 ({attempt}/{args.tries}): {problem}")
        else:
            print(f"{spec['id']} 실패 — {out_dir / 'case.md'} 를 열어 보세요")


if __name__ == "__main__":
    main()
