"""조회 API. 코어 에이전트와 채점 에이전트가 쓰는 함수는 모두 MedDB 클래스에 있다.

상태는 호출하는 쪽이 들고 있고, 여기 함수들은 상태를 인자로 받아 답만 돌려준다.
  present / absent : 있음·없음으로 확인된 소견 id
  asked            : 이미 물어본 슬롯 id (발생 시점, 과거력 등 자유 응답 항목)
  exams_done       : 이미 시행한 진찰 id
모델 호출이나 네트워크 접근은 없다.
"""
from __future__ import annotations

import math
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .build import DATA_DIR, _read_tsv_gz, build, load_sources

W_PRESENT = {"key": 3.0, "support": 1.0, "against": -2.0}
W_ABSENT = {"key": -1.5, "support": -0.3, "against": 0.0}
# 아래 두 감점은 tools/eval_kb.py 로 비교해 보니 정확도를 떨어뜨려(71% → 61~69%) 0으로 둔다.
# 정답 질환도 아직 묻지 않은 핵심 소견을 갖는 경우가 많기 때문. 근거 없는 후보는 최종 선택 단계에서 거른다.
W_UNKNOWN_KEY = 0.0  # 아직 확인하지 않은 핵심 소견 하나당 감점
W_NO_EVIDENCE = 0.0  # 확인된 핵심 소견이 하나도 없는 질환의 추가 감점
W_FREQ = 0.5
W_PREV = 0.5       # 진료 통계 사전확률 가중치
PREV_ZERO = 3.0    # 해당 성·연령 칸에서 전체의 0.1%를 차지하면 0점
PREV_CLIP = (-2.0, 1.5)
AGE_PENALTY = 3.0
STAGE_ORDER = ("hpi", "red_flag", "core", "exam", "discriminate", "background")

# 공식 초진 기록의 칸 (nova_sdk 1.0.0의 RECORD_FIELDS와 같다). 칸이 빠지거나 다른 칸이 있으면 제출이 거절된다.
# 주진단은 기록 안이 아니라 client.diagnose(note=..., diagnosis=...)의 별도 인자다.
NOTE_FIELDS = {"S": ("cc", "hpi", "pmh", "fh", "sh", "ros"), "O": ("exam", "tests"),
               "A": ("evidence", "differential"),
               "P": ("tests", "treatment", "disposition", "follow_up", "education")}
_SOAP_TO_FIELD = {"S.현병력": "hpi", "S.과거력": "pmh", "S.약물": "pmh", "S.알레르기": "pmh", "S.가족력": "fh",
                  "S.사회력": "sh", "O.진찰": "exam", "O.활력징후": "exam"}
_VITAL_ORDER = ("BP", "SBP", "DBP", "HR", "RR", "BT", "SpO2")
_VITAL_KEYS = {"bp": "BP", "혈압": "BP", "sbp": "SBP", "dbp": "DBP", "hr": "HR", "pr": "HR", "pulse": "HR", "맥박": "HR",
               "심박수": "HR", "rr": "RR", "호흡수": "RR", "bt": "BT", "temp": "BT", "temperature": "BT", "체온": "BT",
               "spo2": "SpO2", "sao2": "SpO2", "산소포화도": "SpO2"}
_VITAL_TEXT = re.compile(r"(혈압|맥박|심박수|호흡수|체온|산소포화도|bp|sbp|dbp|hr|pr|rr|bt|spo2|sao2)\s*[:=]?\s*"
                         r"(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)", re.I)


def parse_vitals(vitals) -> dict:
    """활력징후를 {BP, SBP, DBP, HR, RR, BT, SpO2} 키로 맞춘다. dict(키 대소문자·한글 무관)나
    "BP 150/90, HR 102" 같은 문자열을 받는다. 대회 세션의 vital_signs 형식은 샘플로 확인이 필요하다."""
    out: dict = {}
    if isinstance(vitals, str):
        pairs = [(m.group(1), m.group(2)) for m in _VITAL_TEXT.finditer(vitals)]
    elif isinstance(vitals, dict):
        pairs = list(vitals.items())
    else:
        return out
    for key, value in pairs:
        name = _VITAL_KEYS.get(str(key).strip().lower().replace(" ", "").replace("_", ""))
        if name is None or value is None:
            continue
        text = str(value).strip()
        if name == "BP" and "/" in text:
            out["BP"] = text.replace(" ", "")
            try:
                out["SBP"], out["DBP"] = (float(x) for x in out["BP"].split("/")[:2])
            except ValueError:
                pass
            continue
        number = re.search(r"\d+(?:\.\d+)?", text)
        if number:
            out[name] = float(number.group())
    return out

_NEG = ("없", "않", "아니", "안 ", "못 ")
_UNKNOWN = ("모르", "기억 안", "기억이 안", "확실하지", "잘 몰", "글쎄")
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
    def __init__(self, conn: sqlite3.Connection, path: str | Path | None = None):
        self._path = path  # 상병마스터는 처음 쓸 때 읽는다 (4만여 행이라 여는 시간을 줄이려고)
        self._kcd_loaded = False
        conn.row_factory = sqlite3.Row
        q = lambda sql: [dict(r) for r in conn.execute(sql)]  # noqa: E731
        self.meta = {r["key"]: r["value"] for r in q("SELECT * FROM meta")}
        self.slots = {r["id"]: r for r in q("SELECT * FROM slot")}
        self.exams = {r["id"]: r for r in q("SELECT * FROM exam")}
        self.findings = {r["id"]: r for r in q("SELECT * FROM finding")}
        self.diseases = {r["id"]: r for r in q("SELECT * FROM disease")}
        self.complaints = {r["id"]: r for r in q("SELECT * FROM complaint")}
        self.roles: dict[str, dict[str, str]] = defaultdict(dict)  # disease -> finding -> role
        self.sources: dict[str, dict[str, str]] = defaultdict(dict)  # disease -> finding -> 출처
        self.rule_out: dict[str, list[str]] = defaultdict(list)
        for r in q("SELECT * FROM disease_finding"):
            self.roles[r["disease_id"]][r["finding_id"]] = r["role"]
            self.sources[r["disease_id"]][r["finding_id"]] = r["source"]
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
        self.kcd_names: dict[str, str] = {}    # 코드 → 대표 이름
        self.kcd_by_name: dict[str, str] = {}  # 정규화한 이름 → 코드 (대표 이름 우선)
        # 진료 통계: KB 질환의 KCD 3자리만 남긴다. cell = (성별, 연령군 1~18)
        wanted = {d["kcd"][:3] for d in self.diseases.values() if d["kcd"]}
        self.prev: dict[str, dict[tuple[str, int], int]] = defaultdict(dict)
        self.prev_total: dict[tuple[str, int], int] = defaultdict(int)
        for code, sex_, group, patients in conn.execute("SELECT code, sex, age_group, patients FROM hira"):
            self.prev_total[(sex_, group)] += patients
            if code in wanted:
                self.prev[code][(sex_, group)] = patients
        self.guideline_docs: dict[str, list[dict]] = defaultdict(list)
        for r in q("SELECT * FROM guideline ORDER BY kind, ref_id, seq"):
            self.guideline_docs[r["ref_id"]].append({k: r[k] for k in ("file", "title", "org", "year", "lang", "type", "license")})
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
            build(conn, load_sources(with_kcd=False))
        try:
            return cls(conn, path)
        finally:
            conn.close()

    def _load_kcd(self) -> None:
        if self._kcd_loaded:
            return
        self._kcd_loaded = True
        if self._path is not None:
            conn = sqlite3.connect(f"file:{Path(self._path)}?mode=ro", uri=True)
            try:
                rows = conn.execute("SELECT code, ko, en, main FROM kcd").fetchall()
            finally:
                conn.close()
        else:
            rows = [(r[0], r[1], r[2], int(r[3])) for r in _read_tsv_gz(DATA_DIR / "kcd.tsv.gz")]
        for code, ko, en, main in sorted(rows, key=lambda r: (-r[3], len(r[0]))):
            if main:
                self.kcd_names.setdefault(code, ko)
            for name in (ko, en):
                if name:
                    self.kcd_by_name.setdefault(norm(name), code)

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

    def prior(self, disease_id: str, age: int | None = None, sex: str | None = None) -> float | None:
        """건강보험 진료 통계로 본 사전확률 점수. 그 성·연령 칸의 전체 환자 중 이 질환 KCD 3자리가 차지하는
        비중의 상용로그를 0.1% = 0점으로 맞춘 값(-2 ~ 1.5). 통계가 없으면 None.
        KCD 3자리 단위라 같은 코드를 쓰는 질환끼리는 구분하지 못하고, 외래 만성 질환이 높게 나온다."""
        code = (self.diseases[disease_id]["kcd"] or "")[:3]
        if not self.prev_total or code not in self.prev:
            return None
        group = None if age is None else min(int(age) // 5 + 1, 18)
        cells = [c for c in self.prev_total if (sex is None or c[0] == sex) and (group is None or c[1] == group)]
        total = sum(self.prev_total[c] for c in cells)
        if not total:
            return None
        share = sum(self.prev[code].get(c, 0) for c in cells) / total
        z = PREV_CLIP[0] if share <= 0 else math.log10(share) + PREV_ZERO
        return round(max(PREV_CLIP[0], min(PREV_CLIP[1], z)), 2)

    def kcd_lookup(self, text: str) -> dict | None:
        """상병마스터에서 이름이 정확히 같은(공백·문장부호 무시) 항목을 찾는다."""
        self._load_kcd()
        code = self.kcd_by_name.get(norm(text))
        if code is None:
            return None
        dotted = code if len(code) <= 3 else f"{code[:3]}.{code[3:]}"
        return {"id": None, "ko": self.kcd_names.get(code, text), "kcd": dotted}

    def _known(self, present: Iterable[str], absent: Iterable[str], exams_done: Iterable[str]) -> set[str]:
        known = set(present) | set(absent)
        # Performing an exam does not confirm every finding it can assess.
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
        unknown: list[str] = []
        for clause in _CLAUSE.split(text):
            if not clause or not clause.strip():
                continue
            c = norm(clause)
            negated = any(w in clause + " " for w in _NEG)
            uncertain = any(w in clause for w in _UNKNOWN)
            for alias, fid in self.aliases["finding"]:
                if len(alias) >= 2 and alias in c:
                    bucket = unknown if uncertain else absent if negated else present
                    if fid not in bucket:
                        bucket.append(fid)
        return {"present": present, "absent": [f for f in absent if f not in present],
                "unknown": [f for f in unknown if f not in present and f not in absent]}

    def normalize_diagnosis(self, text: str) -> dict | None:
        """진단명 문자열을 KB 질환으로 맞춘다. 정확히 같은 이름 → 포함 관계(긴 이름 우선) 순.
        KB에 없으면 상병마스터에서 같은 이름을 찾아 {id: None, ko, kcd}를 돌려준다."""
        t = norm(text)
        if not t:
            return None
        exact = [did for alias, did in self.aliases["disease"] if alias == t]
        if exact:
            return self.disease(exact[0])
        partial = [(len(alias), did) for alias, did in self.aliases["disease"]
                   if len(alias) >= 2 and (alias in t or t in alias)]
        return self.disease(max(partial)[1]) if partial else self.kcd_lookup(text)

    def vital_flags(self, vitals: dict) -> list[str]:
        """활력징후에서 바로 알 수 있는 소견. dict나 문자열을 받는다(parse_vitals). 성인 기준."""
        v = parse_vitals(vitals)
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
        d["sources"] = dict(self.sources[disease_id])
        d["plan"] = {k: list(v) for k, v in self.plans[disease_id].items()}
        return d

    def note_field(self, item_id: str) -> str:
        """슬롯·소견·진찰이 공식 기록의 어느 칸에 들어가는지 ("S.hpi", "S.ros", "O.exam" 등).
        증상은 계통 문진(ros), 병력·약물·알레르기는 pmh, 흡연·음주 등은 sh, 진찰 소견과 활력징후는 exam."""
        if item_id in self.exams:
            return "O.exam"
        if item_id in self.slots:
            return "S." + _SOAP_TO_FIELD[self.slots[item_id]["soap"]]
        f = self.findings[item_id]
        if f["kind"] == "symptom":
            return "S.ros"
        field = _SOAP_TO_FIELD[f["soap"]]
        return ("O." if field == "exam" else "S.") + field

    def describe(self, ids: Iterable[str]) -> list[dict]:
        """슬롯·소견·진찰 id의 한국어 이름과 기록 위치. note는 공식 기록의 칸."""
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
            else:
                continue
            out[-1]["note"] = self.note_field(i)
        return out

    # ---- 초진 기록(SOAP) -----------------------------------------------------
    @staticmethod
    def empty_note() -> dict[str, dict[str, str]]:
        """공식 칸을 모두 갖춘 빈 기록. nova_sdk.empty_record()와 같은 구조다."""
        return {section: {field: "" for field in fields} for section, fields in NOTE_FIELDS.items()}

    def record(self, complaint: str, present: Iterable[str] = (), absent: Iterable[str] = (),
               answers: dict[str, str] | None = None, turns: dict[str, int] | None = None,
               vitals=None, exam_results: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
        """확인한 사실만으로 S·O 칸을 채운 기록 초안.
          answers       슬롯 id → 환자가 한 답 (예: {"onset": "2시간 전"})
          turns         슬롯·소견·진찰 id → 답을 받은 턴 번호
          exam_results  진찰 id → 받은 결과 문장 (있으면 그 문장을 그대로 적는다)
        표기: 있음 (+), 없음 (-), 묻지 않음 ( ). 넘겨받지 않은 것은 적지 않으므로,
        물어본 것을 present/absent/answers에 빠짐없이 넣어야 기록에 남는다."""
        present, absent = list(dict.fromkeys(present)), list(dict.fromkeys(absent))
        answers, turns, exam_results = answers or {}, turns or {}, exam_results or {}
        known = {**{f: "+" for f in present}, **{f: "-" for f in absent if f not in present}}
        items = self.items[complaint]
        note = self.empty_note()

        def turn(i: str) -> str:
            return f" (턴 {turns[i]})" if i in turns else ""

        def mark(fid: str) -> str:
            return f"{self.findings[fid]['ko']} ({known.get(fid, ' ')})"

        def slot_line(sid: str) -> str:
            return f"{self.slots[sid]['ko']}: {answers[sid]}" if sid in answers else f"{self.slots[sid]['ko']} ( )"

        by_field: dict[str, list[str]] = defaultdict(list)
        for fid in known:
            if fid in self.findings and self.findings[fid]["kind"] in ("history",):
                by_field[self.note_field(fid).split(".")[1]].append(mark(fid))
        background = [ref for _k, ref in self.background]
        for ref in background:  # 공통 병력 중 묻지 않은 것은 빈 괄호로 남긴다
            if ref in self.findings and ref not in known:
                by_field[self.note_field(ref).split(".")[1]].append(mark(ref))

        cc = "C.C : " + self.complaints[complaint]["ko"]
        note["S"]["cc"] = cc + (f" / Onset : {answers['onset']}" if "onset" in answers else " / Onset : ( )")
        hpi = [slot_line(s) for s in items["slot"] if self.note_field(s) == "S.hpi"]
        positives = [self.findings[f]["ko"] for f in present if self.findings[f]["kind"] == "symptom"]
        if positives:
            hpi.append("동반 증상: " + ", ".join(positives))
        note["S"]["hpi"] = "\n".join(hpi + by_field["hpi"])
        pmh_slots = [s for s in dict.fromkeys(list(answers) + background) if s in self.slots and self.note_field(s) == "S.pmh"]
        note["S"]["pmh"] = "\n".join([slot_line(s) for s in pmh_slots] + by_field["pmh"])
        fh_slots = [s for s in dict.fromkeys(list(answers) + background) if s in self.slots and self.note_field(s) == "S.fh"]
        note["S"]["fh"] = "\n".join([slot_line(s) for s in fh_slots] + by_field["fh"])
        note["S"]["sh"] = "\n".join(by_field["sh"])
        ros: dict[str, list[str]] = defaultdict(list)
        symptoms = [f for f in known if self.findings[f]["kind"] == "symptom"]
        symptoms += [f for f in items["finding"] if f not in known and self.findings[f]["kind"] == "symptom"]
        for fid in symptoms:
            ros[self.findings[fid]["sys"]].append(mark(fid))
        note["S"]["ros"] = "\n".join(f"{system}: " + ", ".join(marks) for system, marks in ros.items())

        exam: list[str] = []
        if isinstance(vitals, str) and vitals.strip():
            exam.append("V/S(내원 시): " + vitals.strip())
        elif vitals:
            v = parse_vitals(vitals)
            shown = [f"{k} {v[k]:g}" if isinstance(v[k], float) else f"{k} {v[k]}"
                     for k in _VITAL_ORDER if k in v and not (k in ("SBP", "DBP") and "BP" in v)]
            exam.append("V/S(내원 시): " + ", ".join(shown))
        for eid, text in exam_results.items():
            exam.append(f"{self.exams[eid]['ko']}: {text}{turn(eid)}")
        for fid in known:  # 결과 문장을 따로 받지 않은 진찰 소견
            f = self.findings[fid]
            if f["kind"] == "sign" and f["exam_id"] not in exam_results:
                exam.append(f"{mark(fid)}{turn(fid) or turn(f['exam_id'])}")
        note["O"]["exam"] = "\n".join(exam)
        return note

    def assessment_plan(self, complaint: str, disease_id: str, present: Iterable[str] = (),
                        absent: Iterable[str] = (), turns: dict[str, int] | None = None,
                        age: int | None = None, sex: str | None = None, differentials: int = 3) -> dict:
        """A·P 칸의 초안과 주진단: {"A": {evidence, differential}, "P": {...}, "diagnosis": 주진단}.
        근거에는 확인한 소견만, 감별진단에는 무엇이 없었고 무엇을 확인하지 못했는지 적는다.
        P는 KB의 계획이므로 '앞으로 할 일'이다. 이미 한 것처럼 고쳐 쓰지 말 것."""
        present, absent, turns = set(present), set(absent), turns or {}
        roles = self.roles[disease_id]
        name = lambda f: self.findings[f]["ko"] + (f" (턴 {turns[f]})" if f in turns else "")  # noqa: E731
        support = [name(f) for f in roles if f in present and roles[f] != "against"]
        lines = [f"#1. {self.diseases[disease_id]['ko']}", "- 근거 : " + (", ".join(support) if support else "확인된 소견 부족")]
        negatives = [self.findings[f]["ko"] for f in roles if f in absent and roles[f] == "key"]
        if negatives:
            lines.append("- 맞지 않는 점 : " + ", ".join(negatives) + " 없음")
        others = [c for c in self.candidates(complaint, present, absent, age, sex, k=differentials + 1) if c["id"] != disease_id]
        flagged = [d for d in self.complaint_diseases[complaint]
                   if self.diseases[d]["red_flag"] and d != disease_id and self._fits(self.diseases[d], age, sex)]
        ddx: list[str] = []
        for did in list(dict.fromkeys([c["id"] for c in others[:differentials]] + flagged)):
            r = self.roles[did]
            checks = self.rule_out[did] or [f for f in r if r[f] == "key"]
            none = [self.findings[f]["ko"] for f in checks if f in absent]
            unknown = [self.findings[f]["ko"] for f in checks if f not in absent and f not in present]
            found = [self.findings[f]["ko"] for f in checks if f in present]
            parts = ([", ".join(found) + " 있음"] if found else []) + ([", ".join(none) + " 없음"] if none else []) \
                + ([", ".join(unknown) + " 미확인"] if unknown else [])
            ddx.append(f"r/o {self.diseases[did]['ko']} : " + "; ".join(parts))
        plan = self.plan(disease_id)
        follow = [t for t in plan.get("edu", []) if "내원" in t or "추적" in t or "알리" in t]
        teach = [t for t in plan.get("edu", []) if t not in follow]
        return {"A": {"evidence": "\n".join(lines), "differential": "\n".join(ddx)},
                "P": {"tests": "\n".join(plan.get("test", [])), "treatment": "\n".join(plan.get("treat", [])),
                      "disposition": plan["dispo"], "follow_up": "\n".join(follow), "education": "\n".join(teach)},
                "diagnosis": self.diseases[disease_id]["ko"]}

    def build_note(self, record: dict, assessment: dict) -> tuple[dict[str, dict[str, str]], str]:
        """record()와 assessment_plan()의 결과를 합쳐 client.diagnose(note=..., diagnosis=...)에 넣을 값을 만든다.
        빠진 칸은 빈 문자열로 채우고, 공식 칸이 아닌 것은 버린다."""
        note = self.empty_note()
        for source in (record, assessment):
            for section, fields in NOTE_FIELDS.items():
                for field in fields:
                    value = (source.get(section) or {}).get(field)
                    if value:
                        note[section][field] = str(value)
        return note, str(assessment.get("diagnosis") or "").strip()

    # ---- 진료지침 문서 -------------------------------------------------------
    def guidelines(self, item_id: str, lang: str | None = None, root: str | Path | None = None) -> list[dict]:
        """주호소·질환에 해당하는 대회 진료지침 문서(서지 정보). 제목으로 고른 것이라 앞쪽일수록 믿을 만하다.
        root 또는 환경변수 NOVA_GUIDELINES_DIR 아래에 파일이 있으면 path를 함께 돌려준다."""
        base = Path(root or os.environ.get("NOVA_GUIDELINES_DIR", "") or ".")
        out = []
        for doc in self.guideline_docs.get(item_id, []):
            if lang and doc["lang"] != lang:
                continue
            path = base / doc["file"]
            out.append({**doc, "path": str(path) if path.is_file() else None})
        return out

    @staticmethod
    def read_guideline(path: str | Path, max_chars: int | None = None) -> str | None:
        """문서 본문을 읽는다(머리의 출처·라이선스 포함). 파일이 없으면 None.
        원문을 바꾼 결과물은 배포할 수 없는 문서가 많으므로 읽은 내용은 실행 중에만 쓴다."""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return None
        return text if max_chars is None else text[:max_chars]

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
            prior = self.prior(did, age, sex)
            score = W_FREQ * d["freq"] + W_PREV * (prior or 0.0)
            score += sum(W_PRESENT[roles[f]] for f in present if f in roles)
            score += sum(W_ABSENT[roles[f]] for f in absent if f in roles)
            keys = [f for f, r in roles.items() if r == "key"]
            score -= W_UNKNOWN_KEY * sum(1 for f in keys if f not in present and f not in absent)
            if not any(f in present for f in keys):
                score -= W_NO_EVIDENCE
            if not self._fits(d, age, None):
                score -= AGE_PENALTY
            rows.append({
                "id": did, "ko": d["ko"], "kcd": d["kcd"], "score": round(score, 2), "prior": prior,
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
