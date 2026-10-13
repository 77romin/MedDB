"""하이브리드 에이전트: 대화는 LLM이 이끌고, MedDB(KB)는 매 턴 '지금 무엇이 중요한지'를 알려 준다.

    from examples.hybrid_agent import prepare, consult
    run_agent(prepare, consult)

매 턴의 흐름
  1. KB가 지금까지 확인한 소견으로 상위 감별 후보, 남은 레드플래그, 추천 행동(번호), 진찰표 표준명을 만든다.
  2. LLM이 추천 번호를 고르거나({"pick": 2}) 직접 질문·진찰을 쓴다({"action": "SAY", "content": ...}).
     환자 말에 새 단서가 있으면 추천보다 그 단서를 먼저 따라가도 된다.
  3. 환자 답·진찰 결과를 KB가 소견(있음/없음)으로 바꿔 추적한다. 추천을 고른 경우는 대상 소견을 정확히 알고,
     직접 쓴 질문은 환자 답에서 표현 사전으로 소견을 찾는다.
  4. 끝나면 KB가 확인된 사실로 기록 초안(S·O·A·P)과 진단 순위를 만들고, LLM이 대화 기록과 맞춰 다듬는다.
KB 밖 주호소면 1의 후보·추천 없이 진찰 표준명과 과거력 체크리스트만 주고, 기록은 LLM이 쓴다.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import os

from meddb import MedDB
from examples.consult_skeleton import (NovaError, RETRY_CODES, STOP_CODES, demographics, final_choice,
                                       pick_complaint, read_answer, read_exam, seconds_left, with_retry)

MAX_TURNS = 30          # 50턴 한도 중 쓸 턴
TIME_MARGIN = 180       # 마감 3분 전부터 기록 작성
EXPLAIN_AT = 3          # 남은 턴이 이만큼이면 설명하고 마치라고 알린다
SUGGEST = 6             # 추천 행동 개수
TOP_K = 4               # 프롬프트에 보여 줄 감별 후보 수
HISTORY_LINES = 60      # 프롬프트에 넣을 최근 대화 줄 수
MAX_CHARS = 30

# 진찰표에 자주 나오는 표준 진찰명 (공개 샘플 진찰표의 체계). KB 밖 주호소에서도 진찰 요청 이름으로 쓴다.
COMMON_EXAMS = ("전반적 외관 시진", "의식·지남력 평가", "결막·공막 시진", "경부 림프절 촉진", "갑상선 촉진",
                "흉곽 시진", "폐 청진", "심음 청진", "복부 시진", "장음 청진", "복부 촉진", "간·비장 촉진",
                "하지 말초 진찰", "사지 근력 검사", "심부건반사", "보행 관찰")

STEP_SYSTEM = f"""당신은 외래 진료실의 의사입니다. 가상 환자를 진료합니다. 매번 JSON 객체 하나만 출력하세요.
{{"pick": 번호}}                              [추천 행동] 중 하나를 그대로 수행
{{"action": "SAY", "content": "..."}}         질문 하나 또는 설명 한 마디 ({MAX_CHARS}자 이내)
{{"action": "EXAM", "content": "..."}}        신체 진찰 하나 ({MAX_CHARS}자 이내)
{{"action": "DONE"}}                          진료를 마칠 때
원칙
- 질문은 한 번에 하나. 이미 물었거나 첫마디·대화에 나온 내용은 다시 묻지 않습니다.
- [추천 행동]은 지식베이스가 감별진단을 위해 고른 것입니다. 보통은 추천을 고르고,
  환자 말에서 새 단서가 나오면 그 단서를 먼저 확인합니다. 레드플래그 배제가 우선입니다.
- 진찰은 [표준 진찰명]의 이름을 그대로 써서 "갑상선 촉진을 하겠습니다"처럼 하나만 요청합니다.
  혈액·영상 검사는 진찰이 아니므로 요청하지 않습니다.
- 마치기 전 1~2턴으로 가장 가능성 높은 진단과 다음 검사·치료 계획을 환자에게 쉬운 말로 설명한 뒤 DONE."""

RECORD_SYSTEM = """진료 기록만 근거로 초진 기록을 완성합니다. 확인하지 않은 사실은 쓰지 않습니다.
시작 정보(첫 진술, 활력징후)는 확인된 사실입니다. 입원·초진 기록 말투로 간결하게 씁니다.
(+)/(-)는 대화나 진찰로 확인한 항목에만 쓰고, 확인하지 않은 항목은 ( )로 비워 둡니다.
[지식베이스 초안]이 있으면 그것을 바탕으로 하되, 대화에서 확인된 사실이 빠졌으면 더하고, 대화와 다르면 대화를 따릅니다.
P(계획)는 앞으로 할 일입니다. 주진단은 [진단 순위]와 대화 근거를 함께 보고 하나를 고릅니다.
JSON 객체 하나만 출력하세요. 모든 값은 한국어 문자열(줄바꿈은 \\n)입니다.
{"S": {"cc": "C.C : 주호소 / Onset : 시작 시점", "hpi": "현병력", "pmh": "DM / HTN (-/-), Op. Hx, Medicine history, Allergy",
       "fh": "가족력", "sh": "Smoking, Alcohol, 직업", "ros": "(+)/(-) 목록"},
 "O": {"exam": "V/S와 부위별 진찰 소견", "tests": "검사 결과"},
 "A": {"evidence": "#1. 주진단\\n- 근거 : ...", "differential": "r/o 진단명 : 이유 (한 줄씩)"},
 "P": {"tests": "추가 검사", "treatment": "치료", "disposition": "처치 결정", "follow_up": "추적", "education": "환자 교육"},
 "diagnosis": "주진단 하나"}"""


def prepare():
    return MedDB.open()


def parse_json(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                value, _ = decoder.raw_decode(text, i)
                if isinstance(value, dict):
                    return value
            except ValueError:
                continue
    return None


def chat(client, system: str, user: str, max_tokens: int) -> str:
    reply = with_retry(client.chat, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       max_tokens=max_tokens)
    return reply["choices"][0]["message"]["content"] or ""


def fit(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).strip().strip('"')
    return text[:MAX_CHARS]


class Tracker:
    """KB 쪽 상태: 확인된 소견, 물은 것, 한 진찰, 기록 재료."""

    def __init__(self, db: MedDB, complaint: str | None, age, sex, opening: str, vitals,
                 knowledge_mode='clinical', reference_profile='reviewed'):
        if knowledge_mode not in {'clinical', 'ontology', 'integrated'}:
            raise ValueError('Unknown knowledge mode')
        self.knowledge_mode, self.reference_profile = knowledge_mode, reference_profile
        self.bridge = None
        if knowledge_mode != 'clinical':
            from meddb.bridge import KnowledgeBridge
            self.bridge = KnowledgeBridge(db)
        self.db, self.complaint, self.age, self.sex = db, complaint, age, sex
        self.present: list[str] = []
        self.absent: list[str] = []
        self.asked: set[str] = set()
        self.exams_done: set[str] = set()
        self.answers: dict[str, str] = {}
        self.exam_results: dict[str, str] = {}
        self.turns: dict[str, int] = {}
        self.vitals = vitals
        self.unknown: set[str] = set()
        self.conflicts: set[str] = set()
        self.conflict_turns: dict[str, int] = {}
        self.events: list[dict] = []
        self.exam_attempts: list[dict] = []
        for fid in db.vital_flags(vitals):
            self.mark(fid, '+', 0, str(vitals), 'initial')
        self.note_seen(opening, turn=0)
        when = re.search(r"[^.]*(?:전부터|동안|개월 전|년 전|주 전|일 전|어제|오늘|아침부터)[^.]*\.?", opening)
        if when and "onset" in db.slots:
            self.asked.add("onset")
            self.answers["onset"] = when.group(0).strip()
        self.exam_by_name = {}
        for eid, e in db.exams.items():
            self.exam_by_name[e["ko"]] = eid
            self.exam_by_name[e["action"]] = eid

    def mark(self, fid: str, verdict: str, turn: int, content='', kind='say') -> None:
        old = "+" if fid in self.present else "-" if fid in self.absent else "?"
        self.events.append({"finding_id": fid, "state": verdict, "turn": turn, "content": content, "kind": kind})
        if old != "?" and verdict != "?" and old != verdict:
            self.conflicts.add(fid)
            self.conflict_turns[fid] = turn
            verdict = "?"  # Reconcile contradictory statements before using either.
        elif old == '?' and verdict in {'+', '-'}:
            if fid in self.conflicts and turn <= self.conflict_turns[fid]:
                verdict = '?'  # Parsing the same reply twice is not reconfirmation.
            else:
                self.conflicts.discard(fid)
        for bucket in (self.present, self.absent):
            if fid in bucket:
                bucket.remove(fid)
        self.unknown.discard(fid)
        if verdict == "+":
            self.present.append(fid)
        elif verdict == "-":
            self.absent.append(fid)
        else:
            self.unknown.add(fid)
        self.turns[fid] = turn

    def note_seen(self, text: str, turn: int) -> None:
        """환자 말에서 표현 사전으로 찾은 소견. 직접 묻지 않았어도 환자가 말한 것은 기록한다."""
        found = self.db.match_findings(text or "")
        for fid in found["present"]:
            self.mark(fid, "+", turn, text, 'initial' if turn == 0 else 'say')
        for fid in found["absent"]:
            self.mark(fid, "-", turn, text, 'initial' if turn == 0 else 'say')
        for fid in found.get("unknown", []):
            self.mark(fid, "?", turn, text, 'initial' if turn == 0 else 'say')

    def exam_id(self, text: str) -> str | None:
        if text in self.exam_by_name:
            return self.exam_by_name[text]
        hits = [(len(name), eid) for name, eid in self.exam_by_name.items() if len(name) >= 3 and name in text]
        return max(hits)[1] if hits else None

    # ---- 프롬프트에 넣을 KB 판단 -------------------------------------------------
    def actions(self) -> list[dict]:
        if not self.complaint or self.knowledge_mode == 'ontology':
            return []
        acts = self.db.next_actions(self.complaint, self.present, self.absent, self.asked, self.exams_done,
                                    self.age, self.sex)
        repeat = [self.db._action(fid, 'discriminate', '상충하는 답변 재확인') for fid in sorted(self.conflicts)]
        return [a for a in repeat + acts if a][:SUGGEST]

    def ranked(self, k: int = TOP_K) -> list[dict]:
        if not self.complaint or self.knowledge_mode == 'ontology':
            return []
        return self.db.candidates(self.complaint, self.present, self.absent, self.age, self.sex, k=k)

    def hint(self, acts: list[dict]) -> str:
        db = self.db
        lines = []
        if self.complaint and self.knowledge_mode != 'ontology':
            lines.append(f"[지식베이스 판단] 주호소: {db.complaints[self.complaint]['ko']}")
            for i, c in enumerate(self.ranked(), 1):
                got = ", ".join(db.findings[f]["ko"] for f in c["matched"][:5]) or "없음"
                todo = ", ".join(db.findings[f]["ko"] for f in c["unknown_key"][:3]) or "없음"
                flag = " [레드플래그]" if c["red_flag"] else ""
                bad = ", ".join(db.findings[f]["ko"] + (" 있음" if f in self.present else " 없음")
                                for f in c["against"][:3])
                lines.append(f"  {i}. {c['ko']}{flag} — 확인된 근거: {got} / 아직 확인 안 한 핵심: {todo}"
                             + (f" / 맞지 않는 점: {bad}" if bad else ""))
            if self.absent:
                lines.append("  확인된 '없음': " + ", ".join(db.findings[f]["ko"] for f in self.absent[-8:] if f in db.findings))
            lines.append("[추천 행동]")
            for i, a in enumerate(acts, 1):
                lines.append(f"  {i}. {a['type']} \"{a['text']}\"  ({a['why']})")
            names = [db.exams[e]["ko"] for e in db.items[self.complaint]["exam"]]
            for c in self.ranked():
                for f, role in db.roles[c["id"]].items():
                    ex = db.findings[f].get("exam_id")
                    if role != "against" and ex and db.exams[ex]["ko"] not in names:
                        names.append(db.exams[ex]["ko"])
        else:
            lines.append("[지식베이스 판단] 온톨로지 근거로 진료하세요." if self.knowledge_mode == 'ontology'
                         else "[지식베이스 판단] 이 주호소는 지식베이스 밖입니다. 일반적인 순서로 진료하세요.")
            todo = [] if self.knowledge_mode == 'ontology' else [db.slots[r]["ko"] if r in db.slots else db.findings[r]["ko"]
                    for _, r in db.background if r not in self.asked]
            if todo:
                lines.append("  아직 묻지 않은 기본 항목: " + ", ".join(todo))
            names = []
        names += [n for n in COMMON_EXAMS if n not in names]
        done = {db.exams[e]["ko"] for e in self.exams_done if e in db.exams}
        lines.append("[표준 진찰명] " + ", ".join(n for n in names if n not in done))
        if self.bridge:
            lines.append(self.bridge.hint(self, self.reference_profile))
        if self.conflicts:
            lines.append('[상충 진술: 재확인 필요] ' + ', '.join(sorted(self.conflicts)))
        return "\n".join(lines)


def consult(client, db: MedDB, fallback=None, knowledge_mode=None, reference_profile=None):
    """fallback은 받지만 쓰지 않는다(KB 밖이어도 하이브리드가 진료한다). run.py 연동 모양을 맞추기 위한 인자."""
    session = client.session()
    opening, vitals = session["initial"]["opening"], session["initial"]["vital_signs"]
    age, sex = demographics(opening)
    try:
        complaint = pick_complaint(client, db, opening)
    except NovaError:
        complaint = (db.match_complaint(opening) or [{"id": None}])[0]["id"]
    kb = Tracker(db, complaint, age, sex, opening, vitals,
                 knowledge_mode or os.environ.get('NOVA_KNOWLEDGE_MODE', 'clinical'),
                 reference_profile or os.environ.get('NOVA_REFERENCE_PROFILE', 'reviewed'))
    transcript: list[str] = []
    turn, budget, failures = 0, min(MAX_TURNS, session["turns_remaining"]), 0

    while turn < budget and seconds_left(session) > TIME_MARGIN:
        acts = kb.actions()
        left = budget - turn
        user = (f"[시작 정보] {opening}\n[활력징후] {vitals}\n[대화 기록]\n" + "\n".join(transcript[-HISTORY_LINES:])
                + f"\n[남은 턴] {left}" + ("  ← 이제 진단과 계획을 설명하고 DONE 하세요." if left <= EXPLAIN_AT else "")
                + "\n" + kb.hint(acts))
        try:
            step = parse_json(chat(client, STEP_SYSTEM, user, 2048)) or {}
        except NovaError:
            break
        target = None
        if "pick" in step:
            try:
                pick = step['pick']
                if type(pick) is not int or not 1 <= pick <= len(acts):
                    raise ValueError('Recommendation number must be a positive integer in range')
                act = acts[pick - 1]
            except (ValueError, TypeError, IndexError):
                failures += 1
                if failures >= 3:
                    break
                continue
            kind, text, target = act["type"], act["text"], act["target"]
        else:
            kind = str(step.get("action", "")).upper()
            text = fit(step.get("content", ""))
            if kind == "DONE":
                break
            if kind not in ("SAY", "EXAM") or not text:
                failures += 1
                if failures >= 3:
                    break
                continue
            if kind == "EXAM":
                target = kb.exam_id(text)
        failures = 0
        if kind == "EXAM":
            kb.exam_attempts.append({"target": target, "content": text, "status": "attempted"})
        try:
            if kind == "SAY":
                reply = with_retry(client.say, text)
                turn = reply.get("turn", turn + 1)
                answer = reply["content"]
                transcript += [f"의사: {text}", f"환자: {answer}"]
                if target:
                    kb.asked.add(target)
                    kb.turns.setdefault(target, turn)
                    if target in db.slots:
                        kb.answers[target] = answer
                    else:
                        kb.mark(target, read_answer(client, text, answer, db.findings[target]["ko"]), turn, answer)
                kb.note_seen(answer, turn)
            else:
                reply = with_retry(client.exam, text)
                kb.exam_attempts[-1]["status"] = "completed"
                turn = reply.get("turn", turn + 1)
                transcript.append(f"진찰({text}): {reply['result']}")
                if target:
                    kb.exams_done.add(target)
                    kb.turns.setdefault(target, turn)
                    kb.exam_results[target] = reply["result"]
                    signs = [db.findings[f] for f in db.exam_findings.get(target, []) if f in db.findings]
                    for fid, verdict in read_exam(client, reply["result"], signs).items():
                        kb.mark(fid, verdict, turn, reply['result'], 'exam')
        except NovaError as exc:
            code = getattr(exc, "code", "")
            if kind == "EXAM":
                kb.exam_attempts[-1]["status"] = "rejected"
                kb.exam_attempts[-1]["code"] = code
            if code in STOP_CODES or code in RETRY_CODES:
                break
            turn += 1  # 거절된 진찰도 1턴을 쓴다(10/11 규칙)
            hint = "신체진찰이 아닙니다" if code == "EXAM_NOT_RECOGNIZED" else "하나만 구체적으로, 표준 진찰명으로"
            transcript.append(f"(알림: {text} 요청 거절 {code}. {hint})")

    note, diagnosis = write_record(client, db, kb, opening, vitals, transcript)
    return client.diagnose(note=note, diagnosis=diagnosis)


def write_record(client, db: MedDB, kb: Tracker, opening, vitals, transcript):
    """KB 초안(확인된 사실만) → LLM이 대화와 맞춰 다듬음. LLM이 실패하면 KB 초안을 그대로 낸다."""
    draft, draft_dx, ranking = None, "", ""
    if kb.complaint and kb.knowledge_mode != 'ontology':
        ranked = kb.ranked(k=5)
        top = final_choice(ranked)
        record = db.record(kb.complaint, kb.present, kb.absent, answers=kb.answers, turns=kb.turns,
                           vitals=vitals, exam_results=kb.exam_results)
        assessment = db.assessment_plan(kb.complaint, top["id"], kb.present, kb.absent, turns=kb.turns,
                                        age=kb.age, sex=kb.sex)
        draft, draft_dx = db.build_note(record, assessment)
        ranking = "\n".join(f"{i}. {c['ko']} (근거 {len(c['matched'])}개)" for i, c in enumerate(ranked, 1))
    user = f"[시작 정보] {opening}\n[활력징후] {vitals}\n[대화 기록]\n" + "\n".join(transcript)
    if draft:
        user += f"\n[지식베이스 초안]\n{json.dumps(draft, ensure_ascii=False)}\n[진단 순위]\n{ranking}"
    if kb.bridge:
        user += '\n' + kb.bridge.hint(kb, kb.reference_profile)
    for _ in range(2):
        try:
            result = parse_json(chat(client, RECORD_SYSTEM, user, 4096)) or {}
        except NovaError:
            break
        note = MedDB.empty_note()
        for section, fields in note.items():
            got = result.get(section) if isinstance(result.get(section), dict) else {}
            for field in fields:
                value = got.get(field, "")
                note[section][field] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        diagnosis = str(result.get("diagnosis") or "").strip()
        if diagnosis and any(note[s][f] for s in note for f in note[s]):
            if draft:  # LLM이 비운 칸은 KB 초안으로 채운다
                for s in note:
                    for f in note[s]:
                        if s in ("S", "O"):
                            note[s][f] = note[s][f] or draft[s][f]
                chosen = db.normalize_diagnosis(diagnosis)
                if chosen and chosen.get("id"):
                    consistent = db.assessment_plan(kb.complaint, chosen["id"], kb.present, kb.absent,
                                                    turns=kb.turns, age=kb.age, sex=kb.sex)
                    note["A"], note["P"] = consistent["A"], consistent["P"]
                    diagnosis = chosen["ko"]
                elif not note["A"]["evidence"].strip().startswith("#1. " + diagnosis):
                    # No KB plan exists for this diagnosis: never reuse another disease's plan.
                    note["A"] = {"evidence": "#1. " + diagnosis, "differential": ""}
                    note["P"] = MedDB.empty_note()["P"]
            return note, diagnosis
    if draft:
        return draft, draft_dx
    note = MedDB.empty_note()
    note["S"]["cc"] = f"C.C : {opening[:60]}"
    note["O"]["exam"] = f"V/S : {vitals}"
    return note, "진단 미정"
