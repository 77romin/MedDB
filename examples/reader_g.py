"""B1g: 온톨로지가 대화를 읽는 부분 보강 (모델 호출 없음, 문진은 건드리지 않음).

1. 나열된 부정: "팔다리 힘이 빠지거나 저린 적, 말이 어눌해진 적은 없다"처럼 서술어 없는 앞 절은
   뒤 절의 부정을 물려받는다 (기존: 마지막 항목만 '없음', 앞 항목은 '있음'으로 잘못 기록).
2. 문맥 확인: 다른 부위·상황에도 쓰이는 표현은 문맥이 맞을 때만 소견으로 잡는다
   ("머리가 조이는" → 가슴 압박 통증 X, "아침에 일어날 때부터 머리가" → 기립 시 증상 X).
3. 일상 표현 보강: "열은 없어요", "진통제를 한 달에 이십 일 넘게" 등.
4. 질문과 답을 함께 읽기: 답에 증상 이름이 없고("아니요, 없어요", "네, 있어요") 질문이 증상 1~2개를 가리키면,
   답의 예/아니요로 그 소견을 '있음/없음'으로 기록한다 (기존: 버려짐).
"""
from __future__ import annotations

import re

from meddb import api as A

PRED = re.compile(r"(있|없|않|아니|안 |못 |했|해요|해서|아파|아프|요|다|죠|네|어|아|고|며|면서|지만|는데|으나|서|데)\s*$")
GUARD = {
    "pressure_chest_pain": re.compile(r"가슴|흉|명치|심장"),
    "orthostatic_sx": re.compile(r"어지|핑|아찔|눈앞|쓰러|기절|휘청"),
    "focal_weakness": re.compile(r"팔|다리|손|발|한쪽|얼굴|마비|반쪽"),
}
EXTRA = {
    "fever": ["열은", "열도", "미열", "열나", "열난"],
    "analgesic_overuse": ["진통제를한달", "진통제를자주", "두통약을매일", "진통제를이십", "진통제를보름", "약을거의매일"],
    "chronic_daily_headache": ["한달에이십일넘게머리", "머리가거의매일"],
}
YES = re.compile(r"^\s*(네|예|응|있어요|있었어요|그래요|맞아요|그런 편|좀 있)")
NO = re.compile(r"^\s*(아니|없어|없었|없습|그런 건 없|그런 적 없|전혀|안 |않)")
UNSURE = re.compile(r"모르|기억이? 안|글쎄|잘 몰")


def install(db) -> None:
    """db 객체에 한 번만: 표현 보강 + match_findings 교체."""
    if getattr(db, "_reader_g", False):
        return
    have = set(db.aliases["finding"])
    for fid, words in EXTRA.items():
        for w in words:
            pair = (A.norm(w), fid)
            if pair not in have:
                db.aliases["finding"].append(pair)
    orig = db.match_findings

    def match_findings(text: str) -> dict:
        parts = re.split("(" + A._CLAUSE.pattern + ")", text or "")
        clauses, delims = [], []
        for i in range(0, len(parts), 2):
            c = parts[i]
            d = parts[i + 1] if i + 1 < len(parts) else ""
            if c and c.strip():
                clauses.append(c.strip())
                delims.append(d or "")
        neg_from_right = False
        pol = [None] * len(clauses)
        for i in range(len(clauses) - 1, -1, -1):
            c, d = clauses[i], delims[i]
            own_neg = any(w in c + " " for w in A._NEG)
            listed = d.strip() == "," and not PRED.search(c)      # 쉼표로 이어진 서술어 없는 항목 ('~한 적,')
            if own_neg:
                pol[i], neg_from_right = "-", True
            elif listed or re.search(r"(적|것)$", c) and d.strip() in ("", ","):
                pol[i] = "-" if neg_from_right else "+"
            else:
                pol[i], neg_from_right = "+", False
        present, absent, unknown = [], [], []
        for c, p in zip(clauses, pol):
            got = orig(c)
            for fid in got["present"] + got["absent"]:
                if fid in GUARD and not GUARD[fid].search(c):
                    continue
                bucket = absent if (p == "-" or fid in got["absent"]) else present
                if fid not in bucket:
                    bucket.append(fid)
            for fid in got["unknown"]:
                if fid not in unknown:
                    unknown.append(fid)
        return {"present": present, "absent": [f for f in absent if f not in present],
                "unknown": [f for f in unknown if f not in present and f not in absent]}

    db.match_findings = match_findings
    db._reader_g = True


def read_qa(kb, db, question: str, answer: str, turn: int) -> None:
    """답에서 증상을 못 찾았을 때만: 질문이 가리키는 소견(1~2개)에 답의 예/아니요를 적용."""
    a = answer or ""
    got = db.match_findings(a)
    if got["present"] or got["absent"] or UNSURE.search(a) or "하나씩" in a:
        return
    pol = "-" if NO.search(a) else "+" if YES.search(a) else None
    if not pol:
        return
    q = db.match_findings(question or "")
    fids = q["present"] + q["absent"]
    if not 1 <= len(fids) <= 2:
        return
    for fid in fids:
        if fid not in kb.present and fid not in kb.absent:
            kb.mark(fid, pol, turn, f"{question} → {a}", "qa")
