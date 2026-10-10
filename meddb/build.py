"""JSON 원본(meddb/data/*.json)을 읽어 검증하고 SQLite로 적재한다. 표준 라이브러리만 사용."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
FILES = ("common", "slots", "exams", "findings", "diseases", "complaints")

SAY_MAX = 30  # 대회 규정: SAY는 한 번에 30자 이하
FINDING_KINDS = {"symptom", "history", "sign", "vital"}
URGENCY = {"emergent", "urgent", "routine"}
PLAN_KINDS = ("test", "treat", "edu", "explain", "unsafe")
VITALS = {"SBP", "DBP", "HR", "RR", "BT", "SpO2"}
OPS = {">=", ">", "<=", "<"}

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_KCD = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")
# 묶은 진찰 요청은 거절되므로 EXAM 문장에 병렬 표현을 두지 않는다.
_EXAM_JOIN = ("그리고", " 및 ", ",", "·", "하고 ", "/")
# 환자·채점 모델에게 지시문처럼 읽힐 수 있는 표현은 KB 문장에 넣지 않는다.
_INJECTION = ("무시하", "무시해", "지시", "시스템", "프롬프트", "채점", "점수", "system", "ignore", "instruction", "prompt")

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE slot(
  id TEXT PRIMARY KEY, ko TEXT NOT NULL, soap TEXT NOT NULL, ask TEXT NOT NULL,
  sex TEXT, age_min INTEGER, age_max INTEGER);
CREATE TABLE exam(id TEXT PRIMARY KEY, ko TEXT NOT NULL, action TEXT NOT NULL);
CREATE TABLE finding(
  id TEXT PRIMARY KEY, ko TEXT NOT NULL, kind TEXT NOT NULL, sys TEXT NOT NULL, soap TEXT NOT NULL,
  ask TEXT, exam_id TEXT REFERENCES exam(id), sex TEXT, age_min INTEGER, age_max INTEGER);
CREATE TABLE disease(
  id TEXT PRIMARY KEY, ko TEXT NOT NULL, en TEXT NOT NULL, kcd TEXT, urgency TEXT NOT NULL,
  red_flag INTEGER NOT NULL, freq INTEGER NOT NULL, sex TEXT, age_min INTEGER, age_max INTEGER,
  dispo TEXT NOT NULL);
CREATE TABLE disease_finding(
  disease_id TEXT NOT NULL REFERENCES disease(id), finding_id TEXT NOT NULL REFERENCES finding(id),
  role TEXT NOT NULL, rule_out INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(disease_id, finding_id));
CREATE TABLE disease_plan(
  disease_id TEXT NOT NULL REFERENCES disease(id), kind TEXT NOT NULL, seq INTEGER NOT NULL, text TEXT NOT NULL);
CREATE TABLE complaint(id TEXT PRIMARY KEY, ko TEXT NOT NULL);
CREATE TABLE complaint_item(
  complaint_id TEXT NOT NULL REFERENCES complaint(id), kind TEXT NOT NULL, ref_id TEXT NOT NULL,
  seq INTEGER NOT NULL);
CREATE TABLE complaint_disease(
  complaint_id TEXT NOT NULL REFERENCES complaint(id), disease_id TEXT NOT NULL REFERENCES disease(id),
  seq INTEGER NOT NULL, PRIMARY KEY(complaint_id, disease_id));
CREATE TABLE background_item(kind TEXT NOT NULL, ref_id TEXT NOT NULL, seq INTEGER NOT NULL);
CREATE TABLE alias(kind TEXT NOT NULL, ref_id TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE vital_rule(finding_id TEXT NOT NULL REFERENCES finding(id), vital TEXT NOT NULL, op TEXT NOT NULL,
  value REAL NOT NULL);
CREATE TABLE phrase(kind TEXT NOT NULL, seq INTEGER NOT NULL, text TEXT NOT NULL);
CREATE INDEX idx_df_finding ON disease_finding(finding_id);
CREATE INDEX idx_alias ON alias(kind, ref_id);
"""


def load_sources(data_dir: Path | str = DATA_DIR) -> dict:
    data_dir = Path(data_dir)
    return {name: json.loads((data_dir / f"{name}.json").read_text(encoding="utf-8")) for name in FILES}


def _age(obj: dict) -> tuple[int | None, int | None]:
    lo, hi = (obj.get("age") or [None, None])
    return lo, hi


def _check_say(text: str, where: str, errors: list[str], question: bool) -> None:
    if len(text) > SAY_MAX:
        errors.append(f"{where}: {len(text)}자 (최대 {SAY_MAX}자) — {text}")
    if question and (text.count("?") != 1 or not text.endswith("?")):
        errors.append(f"{where}: 질문은 물음표 하나로 끝나야 함 — {text}")
    low = text.lower()
    for word in _INJECTION:
        if word in low:
            errors.append(f"{where}: 지시문처럼 읽힐 수 있는 표현 '{word}' — {text}")


def validate(data: dict) -> tuple[list[str], list[str]]:
    """(오류, 경고). 오류가 있으면 빌드하지 않는다."""
    errors: list[str] = []
    warnings: list[str] = []

    def ids(rows: list[dict], label: str) -> set[str]:
        seen: set[str] = set()
        for row in rows:
            rid = row.get("id", "")
            if not _ID.match(rid):
                errors.append(f"{label}: id 형식 오류 '{rid}'")
            if rid in seen:
                errors.append(f"{label}: id 중복 '{rid}'")
            seen.add(rid)
        return seen

    slot_ids = ids(data["slots"], "slots")
    exam_ids = ids(data["exams"], "exams")
    finding_ids = ids(data["findings"], "findings")
    disease_ids = ids(data["diseases"], "diseases")
    ids(data["complaints"], "complaints")
    for a, b, la, lb in ((slot_ids, finding_ids, "slots", "findings"), (exam_ids, finding_ids, "exams", "findings"),
                         (slot_ids, exam_ids, "slots", "exams")):
        for dup in sorted(a & b):
            errors.append(f"{la}/{lb}: id가 겹침 '{dup}'")

    for s in data["slots"]:
        _check_say(s["ask"], f"slots.{s['id']}.ask", errors, question=True)
    for e in data["exams"]:
        act = e["action"]
        _check_say(act, f"exams.{e['id']}.action", errors, question=False)
        if any(j in act for j in _EXAM_JOIN):
            errors.append(f"exams.{e['id']}: 진찰 동작은 하나만 — {act}")

    kinds: dict[str, str] = {}
    for f in data["findings"]:
        fid, kind = f["id"], f.get("kind")
        kinds[fid] = kind
        if kind not in FINDING_KINDS:
            errors.append(f"findings.{fid}: kind 오류 '{kind}'")
        if kind in ("symptom", "history"):
            if not f.get("ask"):
                errors.append(f"findings.{fid}: 질문 문장(ask) 없음")
            else:
                _check_say(f["ask"], f"findings.{fid}.ask", errors, question=True)
        if kind == "sign" and f.get("exam") not in exam_ids:
            errors.append(f"findings.{fid}: 진찰(exam) 참조 오류 '{f.get('exam')}'")
        if not f.get("sys"):
            errors.append(f"findings.{fid}: 계통(sys) 없음")

    used: set[str] = set()
    for d in data["diseases"]:
        did = d["id"]
        if d.get("kcd") is not None and not _KCD.match(d["kcd"]):
            errors.append(f"diseases.{did}: KCD 형식 오류 '{d['kcd']}'")
        if d.get("urgency") not in URGENCY:
            errors.append(f"diseases.{did}: urgency 오류 '{d.get('urgency')}'")
        if d.get("freq") not in (1, 2, 3):
            errors.append(f"diseases.{did}: freq는 1~3")
        roles: dict[str, str] = {}
        for role in ("key", "support", "against"):
            for fid in d.get(role, []):
                if fid not in finding_ids:
                    errors.append(f"diseases.{did}.{role}: 없는 소견 '{fid}'")
                if fid in roles:
                    errors.append(f"diseases.{did}: 소견 '{fid}'가 {roles[fid]}와 {role}에 중복")
                roles[fid] = role
                used.add(fid)
        if len(d.get("key", [])) < 2:
            errors.append(f"diseases.{did}: 핵심 소견(key)은 2개 이상")
        for fid in d.get("rule_out", []):
            if roles.get(fid) not in ("key", "support"):
                errors.append(f"diseases.{did}.rule_out: '{fid}'는 key/support에 있어야 함")
            elif kinds.get(fid) == "vital":
                errors.append(f"diseases.{did}.rule_out: 활력징후 '{fid}'는 물어서 확인할 수 없음")
        if d.get("red_flag") and not d.get("rule_out"):
            errors.append(f"diseases.{did}: red flag 질환은 rule_out 필요")
        plan = d.get("plan", {})
        for kind in ("test", "treat", "edu", "explain"):
            if not plan.get(kind):
                errors.append(f"diseases.{did}.plan.{kind}: 비어 있음")
        for kind in plan:
            if kind not in PLAN_KINDS:
                errors.append(f"diseases.{did}.plan: 알 수 없는 항목 '{kind}'")
        for text in plan.get("explain", []):
            _check_say(text, f"diseases.{did}.plan.explain", errors, question=False)
        if not d.get("dispo"):
            errors.append(f"diseases.{did}: dispo 없음")

    listed: set[str] = set()
    for c in data["complaints"]:
        cid = c["id"]
        for sid in c.get("slots", []):
            if sid not in slot_ids:
                errors.append(f"complaints.{cid}.slots: 없는 슬롯 '{sid}'")
        for fid in c.get("ask", []):
            if fid not in finding_ids:
                errors.append(f"complaints.{cid}.ask: 없는 소견 '{fid}'")
            elif kinds.get(fid) not in ("symptom", "history"):
                errors.append(f"complaints.{cid}.ask: '{fid}'는 물어볼 수 있는 소견이 아님")
            used.add(fid)
        for eid in c.get("exams", []):
            if eid not in exam_ids:
                errors.append(f"complaints.{cid}.exams: 없는 진찰 '{eid}'")
        for did in c.get("diseases", []):
            if did not in disease_ids:
                errors.append(f"complaints.{cid}.diseases: 없는 질환 '{did}'")
            listed.add(did)
        if not c.get("alias"):
            errors.append(f"complaints.{cid}: alias 없음")

    common = data["common"]
    for item in common.get("background", []):
        if item not in slot_ids and item not in finding_ids:
            errors.append(f"common.background: 없는 항목 '{item}'")
        used.add(item)
    for rule in common.get("vital_rules", []):
        if rule["finding"] not in finding_ids:
            errors.append(f"common.vital_rules: 없는 소견 '{rule['finding']}'")
        if rule["vital"] not in VITALS or rule["op"] not in OPS:
            errors.append(f"common.vital_rules: 규칙 오류 {rule}")
        used.add(rule["finding"])
    for kind, texts in common.get("phrases", {}).items():
        for text in texts:
            _check_say(text, f"common.phrases.{kind}", errors, question=False)

    for fid in sorted(finding_ids - used):
        warnings.append(f"findings.{fid}: 어떤 질환·주호소에서도 쓰이지 않음")
    for did in sorted(disease_ids - listed):
        warnings.append(f"diseases.{did}: 어떤 주호소에도 연결되지 않음")
    used_exams = {f.get("exam") for f in data["findings"]} | {e for c in data["complaints"] for e in c.get("exams", [])}
    for eid in sorted(exam_ids - used_exams):
        warnings.append(f"exams.{eid}: 쓰이지 않음")
    return errors, warnings


def build(conn: sqlite3.Connection, data: dict) -> None:
    """검증을 통과한 data를 conn에 적재한다."""
    errors, _ = validate(data)
    if errors:
        raise ValueError("KB 검증 실패:\n" + "\n".join(errors))
    conn.executescript(SCHEMA)
    common = data["common"]
    for key, value in common.get("meta", {}).items():
        conn.execute("INSERT INTO meta VALUES(?,?)", (key, str(value)))
    for s in data["slots"]:
        conn.execute("INSERT INTO slot VALUES(?,?,?,?,?,?,?)",
                     (s["id"], s["ko"], s["soap"], s["ask"], s.get("sex"), *_age(s)))
    for e in data["exams"]:
        conn.execute("INSERT INTO exam VALUES(?,?,?)", (e["id"], e["ko"], e["action"]))
    default_soap = {"symptom": "S.현병력", "history": "S.과거력", "sign": "O.진찰", "vital": "O.활력징후"}
    for f in data["findings"]:
        conn.execute("INSERT INTO finding VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (f["id"], f["ko"], f["kind"], f["sys"], f.get("soap") or default_soap[f["kind"]],
                      f.get("ask"), f.get("exam"), f.get("sex"), *_age(f)))
        for text in f.get("alias", []):
            conn.execute("INSERT INTO alias VALUES('finding',?,?)", (f["id"], text))
    for d in data["diseases"]:
        conn.execute("INSERT INTO disease VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (d["id"], d["ko"], d["en"], d.get("kcd"), d["urgency"], int(bool(d.get("red_flag"))),
                      d["freq"], d.get("sex"), *_age(d), d["dispo"]))
        rule_out = set(d.get("rule_out", []))
        for role in ("key", "support", "against"):
            for fid in d.get(role, []):
                conn.execute("INSERT INTO disease_finding VALUES(?,?,?,?)", (d["id"], fid, role, int(fid in rule_out)))
        for kind in PLAN_KINDS:
            for seq, text in enumerate(d["plan"].get(kind, [])):
                conn.execute("INSERT INTO disease_plan VALUES(?,?,?,?)", (d["id"], kind, seq, text))
        for text in d.get("alias", []):
            conn.execute("INSERT INTO alias VALUES('disease',?,?)", (d["id"], text))
    for c in data["complaints"]:
        conn.execute("INSERT INTO complaint VALUES(?,?)", (c["id"], c["ko"]))
        seq = 0
        for kind, key in (("slot", "slots"), ("finding", "ask"), ("exam", "exams")):
            for ref in c.get(key, []):
                conn.execute("INSERT INTO complaint_item VALUES(?,?,?,?)", (c["id"], kind, ref, seq))
                seq += 1
        for seq, did in enumerate(c.get("diseases", [])):
            conn.execute("INSERT INTO complaint_disease VALUES(?,?,?)", (c["id"], did, seq))
        for text in c["alias"]:
            conn.execute("INSERT INTO alias VALUES('complaint',?,?)", (c["id"], text))
    for seq, item in enumerate(common.get("background", [])):
        conn.execute("INSERT INTO background_item VALUES(?,?,?)",
                     ("slot" if any(s["id"] == item for s in data["slots"]) else "finding", item, seq))
    for rule in common.get("vital_rules", []):
        conn.execute("INSERT INTO vital_rule VALUES(?,?,?,?)", (rule["finding"], rule["vital"], rule["op"], rule["value"]))
    for kind, texts in common.get("phrases", {}).items():
        for seq, text in enumerate(texts):
            conn.execute("INSERT INTO phrase VALUES(?,?,?)", (kind, seq, text))
    conn.commit()


def build_file(path: Path | str, data_dir: Path | str = DATA_DIR) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        build(conn, load_sources(data_dir))
        conn.execute("VACUUM")
    finally:
        conn.close()
    return path
