"""검증 세트(dev_cases/)를 로컬에서 돌리고 표로 요약한다. nova-starter 폴더에서 실행.

    python local/run_dev.py --agent meddb               # 전부 실행 후 요약
    python local/run_dev.py --agent baseline
    python local/run_dev.py --summary-only              # 이미 돌린 결과(local/out/dev_*.json)만 요약
    python local/run_dev.py --agent meddb --split dev   # dev만 (test는 점수만 보고 KB를 맞추지 않는다)

진단 정답 판정: KB 질환으로 맞춰서 같은 질환이거나, KCD 앞 3자리가 같거나, 이름이 서로 포함되면 정답.
판정이 애매한 것은 '?'로 표시하니 사람이 확인한다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from case_md_to_json import convert  # noqa: E402
from meddb import MedDB  # noqa: E402


def core(name: str) -> str:
    return re.sub(r"\(.*?\)|\s|[·,]", "", name or "").lower()


def same_dx(db: MedDB, submitted: str, answer: str) -> str:
    """'O' 정답, 'X' 오답, '?' 사람이 확인."""
    if not submitted:
        return "X"
    a, b = core(submitted), core(answer)
    if a and b and (a in b or b in a):
        return "O"
    na, nb = db.normalize_diagnosis(submitted), db.normalize_diagnosis(answer)
    if na and nb:
        if na.get("id") and na.get("id") == nb.get("id"):
            return "O"
        ka, kb = (na.get("kcd") or "")[:3], (nb.get("kcd") or "")[:3]
        if ka and kb:
            return "O" if ka == kb else "X"
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["baseline", "meddb", "hybrid"], default="meddb")
    ap.add_argument("--cases", default=str(ROOT / "dev_cases"))
    ap.add_argument("--specs", default=str(HERE / "dev_specs.json"))
    ap.add_argument("--split", choices=["dev", "test", "all"], default="all")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    specs = {s["id"]: s for s in json.loads(Path(args.specs).read_text(encoding="utf-8"))["cases"]}
    db = MedDB.open()
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    rows = []
    for folder in sorted(Path(args.cases).glob("*/")):
        cid = folder.name
        spec = specs.get(cid, {})
        if args.split != "all" and spec.get("split") != args.split:
            continue
        if not (folder / "case.md").exists():
            continue
        case = convert(folder / "case.md", f"dev_{cid}", spec.get("diagnosis", ""))
        case_json = HERE / "cases" / "dev" / f"{cid}.json"
        case_json.parent.mkdir(parents=True, exist_ok=True)
        case_json.write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
        result = out / f"dev_{cid}_{args.agent}.json"
        if not args.summary_only:
            print(f"--- {cid} ({args.agent}) {spec.get('diagnosis', '')}", flush=True)
            with open(out / f"dev_{cid}_{args.agent}.txt", "w", encoding="utf-8") as log:
                subprocess.run([sys.executable, str(HERE / "local_run.py"), "--case", str(case_json),
                                "--agent", args.agent], stdout=log, stderr=subprocess.STDOUT, check=False)
        if not result.exists():
            continue
        r = json.loads(result.read_text(encoding="utf-8"))
        submitted = (r.get("submitted") or {}).get("diagnosis", "")
        routed = [h["id"] for h in db.match_complaint(case["opening"])][:1]
        rejected = sum(1 for e in r.get("log", []) if str(e.get("result", "")).startswith("EXAM_NOT"))
        no_finding = sum(1 for e in r.get("log", []) if e.get("kind") == "EXAM" and e.get("result") == "특이 소견 없음")
        rows.append({"id": cid, "split": spec.get("split", "?"), "answer": case["answer"]["diagnosis"],
                     "submitted": submitted, "ok": same_dx(db, submitted, case["answer"]["diagnosis"]),
                     "routed": routed[0] if routed else "(기본 에이전트)", "turns": r.get("turns"),
                     "rejected": rejected, "no_finding": no_finding, "seconds": r.get("seconds")})
    if not rows:
        print("결과가 없습니다. 먼저 local/gen_cases.py 로 dev_cases/ 를 만드세요.")
        return
    print(f"\n{'ID':<4} {'구분':<4} {'판정':<2} {'턴':>3} {'거절':>3} {'소견없음':>4}  {'라우팅':<16} 제출 진단  ←  정답")
    for x in rows:
        print(f"{x['id']:<4} {x['split']:<4} {x['ok']:<2} {x['turns']:>3} {x['rejected']:>3} {x['no_finding']:>4}  "
              f"{x['routed']:<16} {x['submitted']}  ←  {x['answer']}")
    for split in ("dev", "test", "all"):
        sub = [x for x in rows if split == "all" or x["split"] == split]
        if not sub:
            continue
        ok = sum(x["ok"] == "O" for x in sub)
        unsure = sum(x["ok"] == "?" for x in sub)
        routed = [x for x in sub if not x["routed"].startswith("(")]
        print(f"[{split}] {len(sub)}건  정답 {ok} ({ok / len(sub):.0%}, 확인 필요 {unsure})  "
              f"KB 라우팅 {len(routed)}건 중 정답 {sum(x['ok'] == 'O' for x in routed)}  "
              f"평균 턴 {sum(x['turns'] or 0 for x in sub) / len(sub):.1f}  거절 {sum(x['rejected'] for x in sub)}")
    summary = out / f"dev_summary_{args.agent}.json"
    summary.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장:", summary)


if __name__ == "__main__":
    main()
