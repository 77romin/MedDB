"""KB 자기일관성 평가: 공개 샘플을 쓰지 않고 KB의 모든 (주호소, 질환) 쌍을 가상 환자로 돌려 본다.

    python tools/eval_kb.py                 # 요약
    python tools/eval_kb.py --misses        # 틀린 쌍 목록
    python tools/eval_kb.py --seeds 5 --keep 0.6

가상 환자: 그 질환의 key 소견은 --keep 확률로, support 소견은 절반 확률로 갖고, 나머지는 없다.
에이전트(examples/consult_skeleton.consult)가 스스로 고른 질문·진찰만으로 진단에 도달하는지 본다.
모델 호출은 정답 상태를 그대로 돌려주는 가짜이므로, '듣고 본 것을 제대로 읽었을 때'의 KB 성능이다.
임상적 타당성 검증이 아니라 점수 체계·질문 선택의 결함(예: 묻지 않은 질환이 1위가 되는 문제)을 찾는 도구다.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from meddb import MedDB  # noqa: E402
import examples.consult_skeleton as sk  # noqa: E402


import json  # noqa: E402

ALIASES = {c["id"]: c["alias"] for c in json.loads((ROOT / "meddb" / "data" / "complaints.json").read_text(encoding="utf-8"))}


class Patient:
    def __init__(self, db: MedDB, opening: str, truth: set[str]):
        self.db, self.opening, self.truth = db, opening, truth
        self.turns, self.submitted = 50, None
        self.ask_to_finding = {f["ask"]: fid for fid, f in db.findings.items() if f.get("ask")}
        self.ko_to_finding = {f["ko"]: fid for fid, f in db.findings.items()}
        self.exam_by_action = {e["action"]: eid for eid, e in db.exams.items()}

    def session(self):
        return {"initial": {"opening": self.opening, "vital_signs": "혈압 120/80 mmHg, 맥박 80 회/분, 호흡 16 회/분, 체온 36.8°C"},
                "turns_remaining": self.turns}

    def say(self, text):
        self.turns -= 1
        fid = self.ask_to_finding.get(text)
        if fid is None:
            answer = "네, 알겠습니다."
        else:
            answer = "네, 그래요." if fid in self.truth else "아니요, 없어요."
        return {"content": answer, "turns_remaining": self.turns}

    def exam(self, text):
        self.turns -= 1
        eid = self.exam_by_action[text]
        parts = [f"{self.db.findings[f]['ko']}({'+' if f in self.truth else '-'})"
                 for f in self.db.exam_findings.get(eid, [])]
        return {"result": ", ".join(parts) or "특이 소견 없음", "turns_remaining": self.turns}

    def chat(self, messages, max_tokens=2048, **_):
        q = messages[-1]["content"]
        m = re.search(r"이 결과에 '(.*)' 소견", q) or re.search(r"\[소견\] (.*)\n", q)
        if m:
            fid = self.ko_to_finding.get(m.group(1))
            out = "+" if fid in self.truth else "-"
        elif "주호소를 다음 중" in q:
            out = "none"
        else:
            out = "?"
        return {"choices": [{"message": {"content": out}}]}

    def diagnose(self, note, diagnosis):
        self.submitted = (note, diagnosis)
        return {"ok": True}


def demographics_for(d: dict, rng: random.Random) -> tuple[int, str]:
    lo, hi = (d.get("age") or [None, None])
    lo = 18 if lo is None else lo
    hi = 80 if hi is None else hi
    if lo > hi:
        lo, hi = hi, lo
    age = rng.randint(lo, max(lo, min(hi, lo + 40)))
    sex = d.get("sex") or rng.choice("MF")
    return age, sex


def opening_for(db: MedDB, complaint: str, age: int, sex: str) -> str:
    alias = ALIASES[complaint][0]
    who = f"{age}세 {'남자' if sex == 'M' else '여자'}"
    return f"{who}입니다. {alias} 병원에 왔어요."


def run(seeds: int, keep: float, show_misses: bool) -> dict:
    db = sk.prepare()
    stats = defaultdict(lambda: [0, 0, 0])  # complaint -> [n, top1, top3]
    misses = []
    for cid, c in db.complaints.items():
        for did in db.complaint_diseases[cid]:
            d = db.diseases[did]
            roles = db.roles[did]
            for seed in range(seeds):
                rng = random.Random(f"{cid}/{did}/{seed}")
                age, sex = demographics_for(d, rng)
                keys = [f for f, r in roles.items() if r == "key"]
                sup = [f for f, r in roles.items() if r == "support"]
                truth = {f for f in keys if rng.random() < keep} | {f for f in sup if rng.random() < 0.5}
                if not truth & set(keys):
                    truth.add(rng.choice(keys))   # 핵심 소견이 하나도 없는 환자는 진단 불가이므로 하나는 둔다
                opening = opening_for(db, cid, age, sex)
                patient = Patient(db, opening, truth)
                seen = {}
                original = db.candidates

                def recording(*a, **kw):          # consult가 마지막에 본 상태로 상위 3위를 다시 계산하기 위해
                    seen["args"], seen["kw"] = a, kw
                    return original(*a, **kw)
                db.candidates = recording
                try:
                    sk.consult(patient, db)
                finally:
                    db.candidates = original
                note, diagnosis = patient.submitted
                ranked = [r["id"] for r in original(*seen["args"], **{**seen["kw"], "k": 3})]
                got = db.normalize_diagnosis(diagnosis) or {}
                hit1 = got.get("id") == did
                s = stats[cid]
                s[0] += 1
                s[1] += hit1
                s[2] += hit1 or did in ranked
                if not hit1:
                    misses.append((cid, did, got.get("id"), age, sex, sorted(truth)))
    total = [sum(v[i] for v in stats.values()) for i in range(3)]
    print(f"{'주호소':<18} {'n':>4} {'1위':>6} {'상위3':>6}")
    for cid, (n, t1, t3) in sorted(stats.items(), key=lambda kv: kv[1][1] / kv[1][0]):
        print(f"{cid:<18} {n:>4} {t1 / n:>6.0%} {t3 / n:>6.0%}")
    print(f"{'전체':<18} {total[0]:>4} {total[1] / total[0]:>6.0%} {total[2] / total[0]:>6.0%}")
    if show_misses:
        print("\n틀린 쌍 (주호소, 정답, 제출, 나이, 성별, 환자가 가진 소견)")
        for row in misses:
            print("  ", row)
    return {"n": total[0], "top1": total[1] / total[0], "top3": total[2] / total[0]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--keep", type=float, default=0.7, help="환자가 각 핵심 소견을 가질 확률")
    ap.add_argument("--misses", action="store_true")
    args = ap.parse_args()
    run(args.seeds, args.keep, args.misses)
