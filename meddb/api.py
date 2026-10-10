"""조회 API. 코어 에이전트와 채점 에이전트가 쓰는 함수는 모두 MedDB 클래스에 있다.

상태는 호출하는 쪽이 들고 있고, 여기 함수들은 상태를 인자로 받아 답만 돌려준다.
  present / absent : 있음·없음으로 확인된 소견 id
  asked            : 이미 물어본 슬롯 id (발생 시점, 과거력 등 자유 응답 항목)
  exams_done       : 이미 시행한 진찰 id
모델 호출이나 네트워크 접근은 없다.
"""
from __future__ import annotations

import math
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .build import build, load_sources

W_PRESENT = {"key": 3.0, "support": 1.0, "against": -2.0}
W_ABSENT = {"key": -1.5, "support": -0.3, "against": 0.0}
W_FREQ = 0.5
AGE_PENALTY = 3.0
STAGE_ORDER = ("hpi", "red_flag", "core", "exam", "discriminate", "background")

_NEG = ("없", "않", "아니", "안 ", "못 ", "모르")
_CLAUSE = re.compile(r"[.!?,\n]|(?<=[가-힣])(?:고|며|면서|지만|는데|으나)\s")
CONFIDENT_SHARE = 0.6  # 1순위 비중이 이보다 크면 감별 질문 대신 1순위의 핵심 소견만 확인한다
GAP = 3  # 주호소 표현 사이에 끼어들 수 있는 글자 수 ("가슴이 너무 아파서")


def norm(text: str) -> str:
    """비교용 정규화: 소문자, 공백·문장부호 제거."""
    return re.sub(r"[\s\.,!?~()\[\]\"'·\-]", "", text.lower())


def _loose(alias: str) -> re.Pattern:
    """띄어 쓴 표현의 어절 사이에 몇 글자가 끼어도 맞도록 한 정규식."""
    return re.compile(f".{{0,{GAP}}}".join(re.escape(norm(tok)) for tok in alias.split() if norm(tok)))


class MedDB:
    def __init__(self, conn: sqlite3.Connection):
        conn.row_factory = sqlite3.Row
        q = lambda sql: [dict(r) for r in conn.execute(sql)]  # noqa: E731
        self.meta = {r["key"]: r["value"] for r in q("SELECT * FROM meta")}
        self.slots = {r["id"]: r for r in q("SELECT * FROM slot")}
        self.exams = {r["id"]: r for r in q("SELECT * FROM exam")}
        self.findings = {r["id"]: r for r in q("SELECT * FROM finding")}
        self.diseases = {r["id"]: r for r in q("SELECT * FROM disease")}
        self.complaints = {r["id"]: r for r in q("SELECT * FROM complaint")}
        self.roles: dict[str, dict[str, str]] = defaultdict(dict)  # disease -> finding -> role
        self.rule_out: dict[str, list[str]] = defaultdict(list)
        for r in q("SELECT * FROM disease_finding"):
            self.roles[r["disease_id"]][r["finding_id"]] = r["role"]
            if r["rule_out"]:
                self.rule_out[r["disease_id"]].append(r["finding_id"])
        self.plans: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for r in q("SELECT * FROM disease_plan ORDER BY disease_id, kind, seq"):
            self.plans[r["disease_id"]][r["kind"]].append(r["text"])
        self.items: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for r in q("SELECT * FROM complaint_item ORDER BY complaint_id, seq"):
            self.items[r["complaint_id"]][r["kind"]].append(r["ref_id"])
        self.complaint_diseases: dict[str, list[str]] = defaultdict(list)
        for r in q("SELECT * FROM complaint_disease ORDER BY complaint_id, seq"):
            self.complaint_diseases[r["complaint_id"]].append(r["disease_id"])
        self.background = [(r["kind"], r["ref_id"]) for r in q("SELECT * FROM background_item ORDER BY seq")]
        self.vital_rules = q("SELECT * FROM vital_rule")
        self.phrases: dict[str, list[str]] = defaultdict(list)
        for r in q("SELECT * FROM phrase ORDER BY kind, seq"):
            self.phrases[r["kind"]].append(r["text"])
        self.aliases: dict[str, list[tuple[str, str]]] = defaultdict(list)  # kind -> [(norm, id)]
        self.complaint_patterns: list[tuple[re.Pattern, int, str]] = []
        for r in q("SELECT * FROM alias"):
            self.aliases[r["kind"]].append((norm(r["text"]), r["ref_id"]))
            if r["kind"] == "complaint":
                self.complaint_patterns.append((_loose(r["text"]), len(norm(r["text"])), r["ref_id"]))
        for kind, table in (("finding", self.findings), ("disease", self.diseases), ("complaint", self.complaints)):
            for rid, row in table.items():
                self.aliases[kind].append((norm(row["ko"]), rid))
                if row.get("en"):
                    self.aliases[kind].append((norm(row["en"]), rid))
        self.exam_findings: dict[str, list[str]] = defaultdict(list)
        for fid, f in self.findings.items():
            if f["exam_id"]:
                self.exam_findings[f["exam_id"]].append(fid)

    # ---- 열기 -------------------------------------------------------------
    @classmethod
    def open(cls, path: str | Path | None = None) -> "MedDB":
        """path가 있으면 빌드된 SQLite 파일을, 없으면 패키지 안 JSON을 메모리에 적재해 연다."""
        if path is not None:
            conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        else:
            conn = sqlite3.connect(":memory:")
            build(conn, load_sources())
        try:
            return cls(conn)
        finally:
            conn.close()

    # ---- 내부 도우미 -------------------------------------------------------
    @staticmethod
    def _fits(row: dict, age: int | None, sex: str | None) -> bool:
        if sex and row.get("sex") and row["sex"] != sex:
            return False
        if age is not None:
            if row.get("age_min") is not None and age < row["age_min"]:
                return False
            if row.get("age_max") is not None and age > row["age_max"]:
                return False
        return True

    def _known(self, present: Iterable[str], absent: Iterable[str], exams_done: Iterable[str]) -> set[str]:
        known = set(present) | set(absent)
        for eid in exams_done:
            known.update(self.exam_findings.get(eid, []))
        return known

    def _action(self, target: str, stage: str, why: str) -> dict | None:
        """슬롯·소견·진찰 id를 실제 행동(SAY/EXAM 문장)으로 바꾼다. 물어볼 수 없는 것은 None."""
        if target in self.slots:
            return {"type": "SAY", "text": self.slots[target]["ask"], "stage": stage, "target": target,
                    "resolves": [], "why": why}
        if target in self.exams:
            return {"type": "EXAM", "text": self.exams[target]["action"], "stage": stage, "target": target,
                    "resolves": list(self.exam_findings.get(target, [])), "why": why}
        f = self.findings[target]
        if f["kind"] == "sign":
            return self._action(f["exam_id"], stage, why)
        if f["kind"] == "vital":
            return None
        return {"type": "SAY", "text": f["ask"], "stage": stage, "target": target, "resolves": [target], "why": why}

    # ---- 주호소·소견·진단명 매칭 ---------------------------------------------
    def match_complaint(self, text: str) -> list[dict]:
        """환자 첫마디에서 주호소 후보를 찾는다(표현 사전 부분 일치). 긴 표현이 맞은 것부터."""
        t = norm(text)
        best: dict[str, int] = {}
        for pattern, size, cid in self.complaint_patterns:
            if pattern.search(t):
                best[cid] = max(best.get(cid, 0), size)
        return [{"id": cid, "ko": self.complaints[cid]["ko"], "matched": n}
                for cid, n in sorted(best.items(), key=lambda kv: -kv[1])]

    def match_findings(self, text: str) -> dict[str, list[str]]:
        """환자 발화에서 소견을 찾는 보조 함수. 절 안에 부정 표현이 있으면 '없음'으로 본다.
        표현 사전에 있는 말만 잡는 휴리스틱이므로, 최종 판정은 호출하는 쪽에서 한다."""
        present: list[str] = []
        absent: list[str] = []
        for clause in _CLAUSE.split(text):
            if not clause or not clause.strip():
                continue
            c = norm(clause)
            negated = any(w in clause + " " for w in _NEG)
            for alias, fid in self.aliases["finding"]:
                if len(alias) >= 2 and alias in c:
                    bucket = absent if negated else present
                    if fid not in bucket:
                        bucket.append(fid)
        return {"present": present, "absent": [f for f in absent if f not in present]}

    def normalize_diagnosis(self, text: str) -> dict | None:
        """진단명 문자열을 KB 질환으로 맞춘다. 정확히 같은 이름 → 포함 관계(긴 이름 우선) 순."""
        t = norm(text)
        if not t:
            return None
        exact = [did for alias, did in self.aliases["disease"] if alias == t]
        if exact:
            return self.disease(exact[0])
        partial = [(len(alias), did) for alias, did in self.aliases["disease"]
                   if len(alias) >= 2 and (alias in t or t in alias)]
        return self.disease(max(partial)[1]) if partial else None

    def vital_flags(self, vitals: dict) -> list[str]:
        """활력징후에서 바로 알 수 있는 소견. 키: SBP, DBP, HR, RR, BT, SpO2 또는 BP="150/90". 성인 기준."""
        v = dict(vitals)
        if isinstance(v.get("BP"), str) and "/" in v["BP"]:
            try:
                v["SBP"], v["DBP"] = (float(x) for x in v["BP"].split("/")[:2])
            except ValueError:
                pass
        out: list[str] = []
        for rule in self.vital_rules:
            try:
                x = float(v[rule["vital"]])
            except (KeyError, TypeError, ValueError):
                continue
            hit = {">=": x >= rule["value"], ">": x > rule["value"],
                   "<=": x <= rule["value"], "<": x < rule["value"]}[rule["op"]]
            if hit and rule["finding_id"] not in out:
                out.append(rule["finding_id"])
        return out

    # ---- 단건 조회 ---------------------------------------------------------
    def disease(self, disease_id: str) -> dict:
        d = dict(self.diseases[disease_id])
        roles = self.roles[disease_id]
        for role in ("key", "support", "against"):
            d[role] = [f for f, r in roles.items() if r == role]
        d["rule_out"] = list(self.rule_out.get(disease_id, []))
        d["plan"] = {k: list(v) for k, v in self.plans[disease_id].items()}
        return d

    def describe(self, ids: Iterable[str]) -> list[dict]:
        """슬롯·소견·진찰 id의 한국어 이름과 SOAP 위치. SOAP의 S·O를 코드로 조립할 때 쓴다."""
        out = []
        for i in ids:
            if i in self.slots:
                s = self.slots[i]
                out.append({"id": i, "ko": s["ko"], "kind": "slot", "soap": s["soap"], "sys": None})
            elif i in self.findings:
                f = self.findings[i]
                out.append({"id": i, "ko": f["ko"], "kind": f["kind"], "soap": f["soap"], "sys": f["sys"]})
            elif i in self.exams:
                out.append({"id": i, "ko": self.exams[i]["ko"], "kind": "exam", "soap": "O.진찰", "sys": None})
        return out

    def vocabulary(self, complaint: str) -> list[dict]:
        """이 주호소에서 쓰이는 소견 목록(id·이름). LLM이 환자 답변을 소견 id로 옮길 때 선택지로 준다."""
        ids: list[str] = list(self.items[complaint]["finding"])
        for did in self.complaint_diseases[complaint]:
            ids += [f for f in self.roles[did] if f not in ids]
        return [{"id": i, "ko": self.findings[i]["ko"], "kind": self.findings[i]["kind"]} for i in ids]

    # ---- 감별진단 ----------------------------------------------------------
    def candidates(self, complaint: str | Iterable[str] | None = None, present: Iterable[str] = (), absent: Iterable[str] = (),
                   age: int | None = None, sex: str | None = None, k: int = 5) -> list[dict]:
        """감별진단 후보를 점수순으로. score는 겹침 점수이고 share는 후보 사이 상대 비중일 뿐 확률이 아니다.
        complaint는 주호소 id 하나 또는 여러 개(동반 주호소). 없으면 전체 질환에서 찾는다."""
        present, absent = set(present), set(absent)
        if complaint is None:
            pool = set(self.diseases)
        else:
            names = [complaint] if isinstance(complaint, str) else list(complaint)
            pool = {d for c in names for d in self.complaint_diseases[c]}
        rows = []
        for did in pool:
            d = self.diseases[did]
            if sex and d["sex"] and d["sex"] != sex:
                continue
            roles = self.roles[did]
            score = W_FREQ * d["freq"]
            score += sum(W_PRESENT[roles[f]] for f in present if f in roles)
            score += sum(W_ABSENT[roles[f]] for f in absent if f in roles)
            if not self._fits(d, age, None):
                score -= AGE_PENALTY
            rows.append({
                "id": did, "ko": d["ko"], "kcd": d["kcd"], "score": round(score, 2),
                "red_flag": bool(d["red_flag"]), "urgency": d["urgency"],
                "matched": [f for f in roles if f in present and roles[f] != "against"],
                "against": [f for f in roles if (f in present and roles[f] == "against")
                            or (f in absent and roles[f] == "key")],
                "unknown_key": [f for f in roles if roles[f] == "key" and f not in present and f not in absent],
            })
        rows.sort(key=lambda r: (-r["score"], r["id"]))
        z = sum(math.exp(r["score"] / 2) for r in rows) or 1.0
        for r in rows:
            r["share"] = round(math.exp(r["score"] / 2) / z, 3)
        return rows[:k]

    def red_flags_pending(self, complaint: str, present: Iterable[str] = (), absent: Iterable[str] = (),
                          exams_done: Iterable[str] = (), age: int | None = None, sex: str | None = None) -> list[dict]:
        """이 주호소에서 반드시 배제해야 하는 질환 중, 배제용 소견을 아직 확인하지 않은 것."""
        known = self._known(present, absent, exams_done)
        out = []
        for did in self.complaint_diseases[complaint]:
            d = self.diseases[did]
            if not d["red_flag"] or not self._fits(d, age, sex):
                continue
            todo = [f for f in self.rule_out[did] if f not in known and self._fits(self.findings[f], age, sex)]
            if todo:
                out.append({"id": did, "ko": d["ko"], "unchecked": todo})
        return out

    # ---- 다음 행동 ---------------------------------------------------------
    def next_actions(self, complaint: str, present: Iterable[str] = (), absent: Iterable[str] = (),
                     asked: Iterable[str] = (), exams_done: Iterable[str] = (), age: int | None = None,
                     sex: str | None = None, limit: int | None = None) -> list[dict]:
        """아직 하지 않은 행동을 우선순위대로. 단계(stage):
        hpi 현병력 슬롯 → red_flag 위험 질환 배제 → core 주호소 필수 문진 → exam 필수 진찰
        → discriminate 상위 후보를 가르는 소견 → background 과거력·약물·알레르기·가족력·사회력.
        같은 문장(진찰 하나가 여러 소견을 확인하는 경우 등)은 한 번만 나온다."""
        present, absent, asked, exams_done = set(present), set(absent), set(asked), set(exams_done)
        known = self._known(present, absent, exams_done)
        items = self.items[complaint]
        out: list[dict] = []
        seen: set[str] = set()

        def push(target: str, stage: str, why: str) -> None:
            row = self.slots.get(target) or self.findings.get(target) or {}
            if not self._fits(row, age, sex):
                return
            if target in asked or target in exams_done or target in known:
                return
            act = self._action(target, stage, why)
            if act is None or act["target"] in exams_done or act["text"] in seen:
                return
            seen.add(act["text"])
            out.append(act)

        for sid in items["slot"]:
            push(sid, "hpi", "현병력")
        for rf in self.red_flags_pending(complaint, present, absent, exams_done, age, sex):
            for fid in rf["unchecked"]:
                push(fid, "red_flag", f"{rf['ko']} 배제")
        for fid in items["finding"]:
            push(fid, "core", "주호소 필수 문진")
        for eid in items["exam"]:
            push(eid, "exam", "주호소 필수 진찰")
        top = self.candidates(complaint, present, absent, age, sex, k=5)
        if top and top[0]["share"] >= CONFIDENT_SHARE:
            for fid in top[0]["unknown_key"]:
                push(fid, "discriminate", f"확인: {top[0]['ko']}")
        else:
            value: dict[str, float] = defaultdict(float)
            for cand in top:
                for fid, role in self.roles[cand["id"]].items():
                    if fid not in known and role != "against":
                        value[fid] += cand["share"] * (1.0 if role == "key" else 0.4)
            total = sum(c["share"] for c in top) or 1.0
            ranked = sorted(((q / total) * (1 - q / total), fid) for fid, q in value.items())
            for split, fid in reversed(ranked):
                if split >= 0.08:
                    owners = [c["ko"] for c in top if self.roles[c["id"]].get(fid) in ("key", "support")]
                    push(fid, "discriminate", "감별: " + " / ".join(owners[:3]))
        for _kind, ref in self.background:
            push(ref, "background", "과거력·사회력")
        out.sort(key=lambda a: STAGE_ORDER.index(a["stage"]))
        return out[:limit] if limit else out

    def ready(self, complaint: str, present: Iterable[str] = (), absent: Iterable[str] = (),
              asked: Iterable[str] = (), exams_done: Iterable[str] = (), age: int | None = None,
              sex: str | None = None) -> dict:
        """DIAGNOSE로 넘어가도 되는지. 필수 단계에 남은 행동이 없으면 ready."""
        acts = self.next_actions(complaint, present, absent, asked, exams_done, age, sex)
        pending: dict[str, list[str]] = defaultdict(list)
        for a in acts:
            if a["stage"] != "discriminate":
                pending[a["stage"]].append(a["target"])
        top = self.candidates(complaint, present, absent, age, sex, k=3)
        margin = round(top[0]["score"] - top[1]["score"], 2) if len(top) > 1 else None
        return {"ready": not pending, "pending": dict(pending), "top": top, "margin": margin}

    # ---- 계획·채점 기준 ------------------------------------------------------
    def plan(self, disease_id: str) -> dict:
        """SOAP의 P에 쓸 재료: test 검사, treat 치료·처치, dispo 처치 결정, edu 교육·추적,
        explain 진단 전 SAY로 할 설명 문장(30자 이하), unsafe 하면 안 되는 처치."""
        p = {k: list(v) for k, v in self.plans[disease_id].items()}
        p["dispo"] = self.diseases[disease_id]["dispo"]
        return p

    def rubric(self, complaint: str, disease_id: str) -> dict:
        """자체 채점 기준 초안. 주의: 가상 증례를 이 KB로 만들면 점수가 부풀려진다(증례는 다른 출처로)."""
        items = self.items[complaint]
        roles = self.roles[disease_id]
        must_ask = list(items["slot"]) + list(items["finding"])
        must_ask += [f for f, r in roles.items() if r == "key" and self.findings[f]["kind"] in ("symptom", "history")
                     and f not in must_ask]
        for did in self.complaint_diseases[complaint]:
            if self.diseases[did]["red_flag"]:
                must_ask += [f for f in self.rule_out[did] if f not in must_ask
                             and self.findings[f]["kind"] != "sign"]
        must_ask += [ref for _k, ref in self.background if ref not in must_ask]
        must_exam = list(items["exam"])
        must_exam += [self.findings[f]["exam_id"] for f, r in roles.items()
                      if r == "key" and self.findings[f]["kind"] == "sign" and self.findings[f]["exam_id"] not in must_exam]
        p = self.plan(disease_id)
        return {"main_dx": self.diseases[disease_id]["ko"], "kcd": self.diseases[disease_id]["kcd"],
                "differentials": [self.diseases[d]["ko"] for d in self.complaint_diseases[complaint] if d != disease_id],
                "must_ask": must_ask, "must_exam": must_exam,
                "expected_plan": p.get("test", []) + p.get("treat", []) + [p["dispo"]] + p.get("edu", []),
                "unsafe": p.get("unsafe", [])}
