"""실험 1 — 하이브리드 B(hybrid_agent.consult) + 의사소통 층.

B의 진료 루프·추천·기록 작성은 그대로 두고, 의사소통에 해당하는 행동만 코드로 더한다.
다른 영역(정보수집·안전)의 규칙은 바꾸지 않아, 점수 변화가 의사소통 층 때문인지 볼 수 있게 했다.

1. 첫 턴: 인사 + 열린 질문 (환자가 스스로 이야기하게 함, 들은 소견은 KB가 추적)
2. 공감: 환자 답에 고통·걱정 표현이 있으면 다음 질문 앞에 공감 한마디 (진료당 최대 2번, 30자 안에서만)
3. 마무리 (진단을 정한 뒤 코드가 진행)
   - 걱정 확인: "가장 걱정되시는 점이 무엇인가요?"
   - 쉬운 말로 진단 설명 → 검사·치료 계획 설명 → 걱정에 대한 답 (모델 1회 호출로 세 문장 작성, 실패 시 KB·기본 문장)
   - 이해 확인: "더 궁금하신 점 있으세요?" → 질문이 오면 한 번 답함
4. B의 "마지막에 모델이 알아서 설명" 규칙은 마무리 단계로 옮겼다(중복 방지).
질문·진찰 단계의 턴 수는 B와 같게(30턴 + 인사 1턴) 두고, 마무리 턴을 그 뒤에 더한다.
마무리 턴은 대부분 모델 호출이 없으므로 Doctor 비용(효율 점수)에 거의 영향이 없다.
"""
from __future__ import annotations

import os
import re
import unicodedata

from meddb import MedDB
from examples import hybrid_agent as H
from examples.consult_skeleton import (NovaError, RETRY_CODES, STOP_CODES, demographics,
                                       pick_complaint, read_answer, read_exam, seconds_left, with_retry)

ASK_TURNS = H.MAX_TURNS + 1   # B의 질문·진찰 턴(30) + 인사 1턴
CLOSING_TURNS = 6             # 걱정 확인 1 + 설명 3 + 궁금한 점 확인 1 + 답 1
TIME_MARGIN = H.TIME_MARGIN
MAX_CHARS = H.MAX_CHARS

GREETING = "안녕하세요. 불편한 점을 자세히 말씀해 주세요."
CONCERN_Q = "마지막으로, 가장 걱정되시는 점이 무엇인가요?"
QUESTIONS_Q = "더 궁금하신 점 있으세요?"
EMPATHY = "많이 힘드셨겠어요. "
EMPATHY_MAX = 2
DISTRESS = re.compile(r"힘들|아파|아프|아팠|괴로|걱정|불안|무서|두려|못 자|잠을 못|우울|답답|지쳐|힘이 없")
QUESTION_CUE = re.compile(r"\?|궁금|어떻게|되나요|될까요|괜찮을까|괜찮은가|해야|있나요|건가요|인가요|나요")
NO_QUESTION = re.compile(r"^(아니|없어|없습|괜찮아요|괜찮습니다|네, 없|네 없|됐어요|감사)")

_OLD_RULE = "- 마치기 전 1~2턴으로 가장 가능성 높은 진단과 다음 검사·치료 계획을 환자에게 쉬운 말로 설명한 뒤 DONE."
assert _OLD_RULE in H.STEP_SYSTEM, "hybrid_agent STEP_SYSTEM 형식이 바뀜 — 실험 1 오버레이 확인 필요"
STEP_SYSTEM = H.STEP_SYSTEM.replace(
    _OLD_RULE,
    "- 진단 설명과 마무리 인사는 진료 마지막에 따로 합니다. 지금은 질문·진찰만 하고, 더 확인할 것이 없으면 DONE.\n"
    "- 직접 쓰는 질문은 환자가 이해하기 쉬운 존댓말로, 의학 용어 없이 씁니다.")

CLOSING_SYSTEM = f"""외래 진료를 마무리하며 환자에게 할 말을 씁니다. 환자는 의학 지식이 없는 일반인입니다.
쉬운 존댓말로, 의학 용어 대신 일상어로 씁니다. 각 문장은 공백 포함 {MAX_CHARS}자 이내, 질문하지 않습니다.
[기록]의 주진단·계획에 없는 새 진단·검사·약은 말하지 않습니다. 확정되지 않았으므로 "가능성이 높아요"처럼 말합니다.
지나치게 안심시키지 말고, 걱정에는 공감한 뒤 무엇을 할지 답합니다.
JSON 하나만 출력: {{"diagnosis": "진단을 쉬운 말로 한 문장", "plan": "다음 검사·치료를 한 문장", "concern": "환자 걱정에 대한 답 한 문장"}}"""

ANSWER_SYSTEM = f"""진료 마지막에 환자가 한 질문에 답합니다. 쉬운 존댓말 한 문장, 공백 포함 {MAX_CHARS}자 이내.
[기록]의 진단·계획 범위 안에서만 답하고, 모르는 것은 검사 후 알려 드린다고 답합니다. 문장만 출력하세요."""


def prepare():
    return MedDB.open()


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", str(text or "")).strip().strip('"').strip()


def _fits(text: str) -> bool:
    return 0 < len(_nfc(text)) <= MAX_CHARS


def consult(client, db: MedDB, fallback=None, knowledge_mode=None, reference_profile=None, coverage=False):
    session = client.session()
    opening, vitals = session["initial"]["opening"], session["initial"]["vital_signs"]
    age, sex = demographics(opening)
    try:
        complaint = pick_complaint(client, db, opening)
    except NovaError:
        complaint = (db.match_complaint(opening) or [{"id": None}])[0]["id"]
    kb = H.Tracker(db, complaint, age, sex, opening, vitals,
                   knowledge_mode or os.environ.get("NOVA_KNOWLEDGE_MODE", "clinical"),
                   reference_profile or os.environ.get("NOVA_REFERENCE_PROFILE", "reviewed"))
    transcript: list[str] = []
    care = None
    if coverage:
        from meddb.coverage import CareCoverage
        care = CareCoverage(db, complaint, age, sex)
    st = {"turn": 0, "stopped": False, "empathy": 0, "distress": False}
    total = session["turns_remaining"]
    ask_budget = min(36 if care else ASK_TURNS, max(1, total - (9 if care else CLOSING_TURNS)))
    failures = 0

    def say(text: str, target: str | None = None, sent: str | None = None) -> str:
        """sent: 실제로 보낼 문장(공감 접두 포함). 소견 판정은 원래 질문 text로 한다."""
        out = sent or text
        reply = with_retry(client.say, out)
        st["turn"] = reply.get("turn", st["turn"] + 1)
        answer = reply["content"]
        transcript.extend([f"의사: {out}", f"환자: {answer}"])
        if care:
            care.observe(target, out, answer, st['turn'])
        if target:
            kb.asked.add(target)
            kb.turns.setdefault(target, st["turn"])
            if target in db.slots:
                kb.answers[target] = answer
            elif target in db.findings:
                kb.mark(target, read_answer(client, text, answer, db.findings[target]["ko"]), st["turn"], answer)
        kb.note_seen(answer, st["turn"])
        st["distress"] = bool(DISTRESS.search(answer or ""))
        return answer

    def with_empathy(text: str) -> str:
        if st["distress"] and st["empathy"] < EMPATHY_MAX and _fits(EMPATHY + text) and "?" in text:
            st["empathy"] += 1
            st["distress"] = False
            return EMPATHY + text
        return text

    # 1) 인사 + 열린 질문
    try:
        say(GREETING)
    except NovaError as exc:
        if getattr(exc, "code", "") in STOP_CODES:
            st["stopped"] = True

    # 2) B와 같은 질문·진찰 루프 (설명 규칙만 마무리 단계로 옮김)
    while not st["stopped"] and st["turn"] < ask_budget and seconds_left(session) > TIME_MARGIN:
        acts = kb.actions()
        required = care.needed(kb) if care else []
        left = ask_budget - st["turn"]
        user = (f"[시작 정보] {opening}\n[활력징후] {vitals}\n[대화 기록]\n"
                + "\n".join(transcript[-H.HISTORY_LINES:]) + f"\n[남은 질문·진찰 턴] {left}\n" + kb.hint(acts))
        if required:
            selected = required[0]
            step = {'action': selected['type'], 'content': selected['text']}
        else:
            try:
                step = H.parse_json(H.chat(client, STEP_SYSTEM, user, 2048)) or {}
            except NovaError:
                break
        target = None
        if "pick" in step:
            pick = step["pick"]
            if type(pick) is not int or not 1 <= pick <= len(acts):
                failures += 1
                if failures >= 3:
                    break
                continue
            act = acts[pick - 1]
            kind, text, target = act["type"], act["text"], act["target"]
        else:
            kind = str(step.get("action", "")).upper()
            raw = _nfc(step.get('content', ''))
            if care and not _fits(raw) and kind != 'DONE':
                failures += 1
                if failures >= 3: break
                continue
            text = raw if care else H.fit(raw)
            if kind == "DONE":
                break
            if kind not in ("SAY", "EXAM") or not text:
                failures += 1
                if failures >= 3:
                    break
                continue
            if kind == "EXAM":
                target = kb.exam_id(text)
            elif care:
                # Link freely written standard questions to the same coverage target.
                from meddb.api import norm
                target = next((fid for fid, row in {**db.slots, **db.findings}.items()
                               if row.get('ask') and norm(row['ask']) == norm(text)), None)
            if required:
                target = selected['target']
        if care and not required and not care.allow_action(kb, kind, text, target):
            transcript.append('(확인된 항목의 반복 또는 연령에 맞지 않는 요청은 생략함)')
            failures += 1
            if failures >= 3: break
            continue
        if care and target:
            care.attempts[target] = care.attempts.get(target, 0) + 1
        failures = 0
        if kind == "EXAM":
            kb.exam_attempts.append({"target": target, "content": text, "status": "attempted"})
        try:
            if kind == "SAY":
                say(text, target, with_empathy(text))
            else:
                reply = with_retry(client.exam, text)
                kb.exam_attempts[-1]["status"] = "completed"
                st["turn"] = reply.get("turn", st["turn"] + 1)
                transcript.append(f"진찰({text}): {reply['result']}")
                if target:
                    kb.exams_done.add(target)
                    kb.turns.setdefault(target, st["turn"])
                    kb.exam_results[target] = reply["result"]
                    signs = [db.findings[f] for f in db.exam_findings.get(target, []) if f in db.findings]
                    for fid, verdict in read_exam(client, reply["result"], signs).items():
                        kb.mark(fid, verdict, st["turn"], reply["result"], "exam")
        except NovaError as exc:
            code = getattr(exc, "code", "")
            if kind == "EXAM" and kb.exam_attempts:
                kb.exam_attempts[-1]["status"] = "rejected"
                kb.exam_attempts[-1]["code"] = code
            if code in STOP_CODES:
                st["stopped"] = True
                break
            if code in RETRY_CODES:
                break
            if care and code not in {'EXAM_NOT_RECOGNIZED', 'EXAM_NOT_SPECIFIC'}:
                # A transport/provider failure is not a completed or rejected clinical action.
                try:
                    current = with_retry(client.session)
                    st['turn'] = total - current['turns_remaining']
                except NovaError:
                    pass
                break
            st["turn"] += 1  # 거절된 진찰도 1턴을 쓴다(10/11 규칙)
            hint = "신체진찰이 아닙니다" if code == "EXAM_NOT_RECOGNIZED" else "하나만 구체적으로, 표준 진찰명으로"
            transcript.append(f"(알림: {text} 요청 거절 {code}. {hint})")

    # 3) 마무리: 걱정 확인 → 기록·진단 확정 → 설명 → 궁금한 점
    def room(n: int = 1) -> bool:
        return (not st["stopped"] and st["turn"] + n <= total and seconds_left(session) > 60)

    concern = ""
    if room(2):
        try:
            concern = say(CONCERN_Q)
        except NovaError as exc:
            st["stopped"] = getattr(exc, "code", "") in STOP_CODES

    note, diagnosis = H.write_record(client, db, kb, opening, vitals, transcript, contextual_plan=bool(care))
    if care:
        care.append_record(note)
    facts_at_record = (tuple(kb.present), tuple(kb.absent), tuple(sorted(kb.unknown)))
    said: list[str] = []
    if room():
        for sentence in _closing_sentences(client, db, note, diagnosis, concern, comprehensive=bool(care)):
            if not room():
                break
            try:
                say(sentence)
                said.append(sentence)
            except NovaError as exc:
                st["stopped"] = getattr(exc, "code", "") in STOP_CODES
                break
        if room(2):
            try:
                reply = say(QUESTIONS_Q)
                if QUESTION_CUE.search(reply or "") and not NO_QUESTION.search(_nfc(reply)):
                    answer = _answer_question(client, note, diagnosis, reply)
                    if room():
                        say(answer)
                        said.append(answer)
            except NovaError:
                pass
    if said:
        line = "환자에게 설명함: " + " / ".join(said)
        note["P"]["education"] = (note["P"]["education"].rstrip() + "\n" + line).strip()
    if care and room():
        # Teach-back asks for understanding rather than equating 'no questions' with understanding.
        try:
            understood = say('집에서 어떻게 하실지 말씀해 주시겠어요?')
            note['P']['education'] += '\n이해 확인 답변: ' + understood
        except NovaError:
            pass
    if care and facts_at_record != (tuple(kb.present), tuple(kb.absent), tuple(sorted(kb.unknown))):
        # New clinical information during closing must not be submitted with a stale record.
        updated, diagnosis = H.write_record(client, db, kb, opening, vitals, transcript, contextual_plan=True)
        care.append_record(updated)
        updated['P']['education'] = (updated['P']['education'] + '\n' + note['P']['education']).strip()
        note = updated
    return client.diagnose(note=note, diagnosis=diagnosis)


def _record_brief(note: dict, diagnosis: str) -> str:
    p = note.get("P", {})
    return (f"[기록]\n주진단: {diagnosis}\n근거: {note.get('A', {}).get('evidence', '')[:300]}\n"
            f"검사 계획: {p.get('tests', '')[:300]}\n치료: {p.get('treatment', '')[:300]}\n"
            f"추적: {p.get('follow_up', '')[:200]}")


def _closing_sentences(client, db: MedDB, note: dict, diagnosis: str, concern: str, comprehensive=False) -> list[str]:
    """[진단 설명, 계획 설명, 걱정에 대한 답]. 모델 1회 호출, 형식·길이가 틀리면 KB 설명·기본 문장으로."""
    chosen = db.normalize_diagnosis(diagnosis) if diagnosis else None
    kb_explain = list(db.plan(chosen["id"]).get("explain", [])) if chosen and chosen.get("id") else []
    fallback = [kb_explain[0] if kb_explain else H.fit(f"{diagnosis} 가능성이 높아요."),
                kb_explain[1] if len(kb_explain) > 1 else "몇 가지 검사로 원인을 확인할게요.",
                "걱정하신 부분도 함께 확인해 볼게요."]
    keys = ('diagnosis', 'plan', 'concern')
    system = CLOSING_SYSTEM
    if comprehensive:
        keys = ('diagnosis', 'plan', 'follow_up', 'safety', 'concern')
        fallback = [kb_explain[0] if kb_explain and _fits(kb_explain[0]) else '증상을 설명할 원인을 찾았어요.',
                    '필요한 검사 후 치료를 정할게요.',
                    '검사 결과를 확인할 재진을 잡을게요.',
                    '갑자기 더 힘들어지면 바로 진료받으세요.',
                    '걱정하신 부분도 함께 확인해 볼게요.']
        system += '\nJSON 키는 diagnosis, plan, follow_up, safety, concern입니다. follow_up은 재진 시점·목적, safety는 기록에 있는 구체적 위험 증상과 대처입니다. 각 문장은 30자 이내로 완결하세요.'
    got = {}
    try:
        user = _record_brief(note, diagnosis) + f"\n[환자 걱정] {concern or '(말하지 않음)'}"
        if comprehensive:
            user += '\n처치 결정: ' + note['P']['disposition'] + '\n교육·주의: ' + note['P']['education']
        got = H.parse_json(H.chat(client, system, user, 1536)) or {}
    except NovaError:
        got = {}
    out = []
    for key, default in zip(keys, fallback):
        text = _nfc(got.get(key, ""))
        out.append(text if _fits(text) and "?" not in text else default)
    if not concern or NO_QUESTION.search(_nfc(concern)):
        out = out[:-1]  # 걱정을 말하지 않았으면 답할 문장은 생략
    return [s for s in out if _fits(s)]


def _answer_question(client, note: dict, diagnosis: str, question: str) -> str:
    default = "검사 결과를 보고 자세히 알려 드릴게요."
    try:
        text = _nfc(H.chat(client, ANSWER_SYSTEM, _record_brief(note, diagnosis) + f"\n[환자 질문] {question}", 1024))
    except NovaError:
        return default
    text = text.splitlines()[0].strip() if text else ""
    return text if _fits(text) and "?" not in text else default
