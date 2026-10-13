"""MedDB를 대회 SDK(nova_sdk 1.0.0)에 붙이는 연동 예시. 완성된 에이전트가 아니라 뼈대다.

    run.py 에서:
        from nova_sdk import run_agent
        from examples.consult_skeleton import prepare, consult
        run_agent(prepare, consult)

흐름은 KB가 정하고(무엇을 물을지, 언제 멈출지), 모델은 환자 답을 있음/없음으로 읽는 데만 쓴다.
프롬프트, 재시도, 시간 관리, 설명 문장 다듬기는 코어 에이전트 쪽에서 채워야 한다.
"""
from __future__ import annotations

import json
import re
import time

from meddb import MedDB

try:  # 대회 SDK가 있으면 그 오류형을, 없으면(단위 테스트) 일반 예외를 잡는다
    from nova_sdk import NovaError
except ImportError:  # pragma: no cover
    NovaError = RuntimeError

TURN_BUDGET = 30        # 필수 단계 14~22턴 + 감별 질문 + 설명 2턴. 한도 50턴에 여유가 있다
EXPLAIN_TURNS = 2
DISCRIMINATE_MAX = 10   # 필수 단계 뒤 감별 행동 최대 수. tools/eval_kb.py 비교: 4→71%, 8→79%, 10→81% (평균 +1턴)
TIME_MARGIN = 180      # 마감 3분 전부터는 기록 작성으로 넘어간다
RETRY_CODES = {"PROVIDER_UNAVAILABLE", "PROVIDER_RESPONSE_INVALID", "PATIENT_RESPONSE_INVALID",
               "EXAMINER_RESPONSE_INVALID", "API_UNAVAILABLE"}   # 서버 쪽 일시 오류, 턴을 쓰지 않음
STOP_CODES = {"TURN_LIMIT_REACHED", "SESSION_EXPIRED", "SESSION_CLOSED", "RUN_NOT_ACTIVE"}
YES = ("네", "예", "맞아", "있어", "있습", "그래", "그렇")
NO = ("아니", "없어", "없습", "없었", "없는", "전혀", "그런 건 없", "그런 적 없")

# 대회 증례는 나이를 "예순두 살", "여섯 살"처럼 한글 수사로 쓴다
_NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50, "예순": 60, "일흔": 70,
                "여든": 80, "아흔": 90}
_NATIVE_ONES = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_SINO = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_AGE_PATTERNS = (
    (re.compile(r"(?<![\d.])(\d{1,3})\s*(?:세|살)"), lambda m: int(m.group(1))),
    (re.compile(r"(?<![\d.])(\d{1,2})\s*개월"), lambda m: int(m.group(1)) // 12),
    (re.compile(r"(?<![가-힣])(열|스물|스무|서른|마흔|쉰|예순|일흔|여든|아흔)?\s?"
                r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)?\s*살"),
     lambda m: _NATIVE_TENS.get(m.group(1) or "", 0) + _NATIVE_ONES.get(m.group(2) or "", 0) or None),
    (re.compile(r"(?<![가-힣])(?:([이삼사오육칠팔구])?십)([일이삼사오육칠팔구])?\s*세"),
     lambda m: _SINO.get(m.group(1) or "", 1) * 10 + _SINO.get(m.group(2) or "", 0)),
)


def prepare():
    """증례에 접근하기 전에 한 번 불린다. 파일을 쓰지 않으므로 읽기 전용 환경에서도 열린다."""
    return MedDB.open()


def parse_age(text: str) -> int | None:
    """문장에서 처음 나오는 나이. 보호자 나이가 뒤에 나와도 환자 나이(앞쪽)를 쓴다."""
    found = []
    for pattern, value in _AGE_PATTERNS:
        for m in pattern.finditer(text):
            age = value(m)
            if age is not None and 0 <= age <= 120:
                found.append((m.start(), age))
                break
    return min(found)[1] if found else None


def demographics(opening: str) -> tuple[int | None, str | None]:
    m = re.search(r"남자|남성|남아|여자|여성|여아", opening)
    sex = None if not m else ("M" if m.group(0).startswith("남") else "F")
    return parse_age(opening), sex


def with_retry(call, *args, **kwargs):
    """서버 쪽 일시 오류(503)는 2·5·10초 뒤 다시 보낸다. 그 밖의 오류는 그대로 올린다."""
    for wait in (2, 5, 10, None):
        try:
            return call(*args, **kwargs)
        except NovaError as exc:
            if getattr(exc, "code", None) not in RETRY_CODES or wait is None:
                raise
            time.sleep(wait)


def ask_model(client, prompt: str, max_tokens: int = 2048) -> str:
    # gpt-oss-20b는 추론 토큰도 max_tokens에 들어가므로 너무 작게 주면 빈 답이 나온다
    reply = with_retry(client.chat, [{"role": "user", "content": prompt}], max_tokens=max_tokens)
    return reply["choices"][0]["message"]["content"] or ""


def seconds_left(session) -> float:
    deadline = session.get("deadline")
    if not deadline:
        return float("inf")
    from datetime import datetime
    return datetime.fromisoformat(str(deadline).replace("Z", "+00:00")).timestamp() - time.time()


def pick_complaint(client, db: MedDB, opening: str) -> str | None:
    """표현 사전으로 못 찾으면 모델에게 고르게 한다. 예선은 증례마다 모델 호출이 1회 이상 있어야 하므로
    사전으로 찾았더라도 확인을 겸해 한 번 묻는다. KB에 맞는 주호소가 없으면 None."""
    hits = db.match_complaint(opening)
    options = ", ".join(f"{c['id']}({c['ko']})" for c in db.complaints.values())
    answer = ask_model(client, f"환자의 첫마디: {opening}\n주호소를 다음 중 하나의 id로만 답하세요. "
                               f"맞는 것이 없으면 none: {options}")
    # 모델 답은 id 하나와 정확히 같을 때만 받는다. 설명 속에 id가 섞인 답으로 엉뚱한 주호소에 가지 않게
    word = re.sub(r"[^a-z_]", "", answer.strip().lower())
    chosen = word if word in db.complaints else None
    return hits[0]["id"] if hits else chosen


def read_answer(client, question: str, answer: str, finding: str | None = None) -> str:
    """환자 답을 '+'(있음), '-'(없음), '?'(알 수 없음)로 읽는다. 뻔한 답은 규칙으로, 나머지는 모델로.
    "약을 안 먹으면 불안해요"처럼 부정어가 들어간 긍정 답이 있으므로 짧은 답만 규칙으로 판정한다."""
    text = answer.strip()
    short = len(text) <= 12
    if any(text.startswith(w) for w in NO) or (short and any(w in text for w in NO)):
        return "-"
    if any(text.startswith(w) for w in YES):
        return "+"
    try:
        target = (f"[소견] {finding}\n이 소견이 환자에게 있으면 +, 없으면 -" if finding
                  else "환자의 답이 '있다'면 +, '없다'면 -")
        # 질문 문장만 주면 "한 달에 한두 번 마셔요"를 과음(+)으로 읽는 일이 있어 판단할 소견 이름을 함께 준다
        verdict = ask_model(client, f"의사: {question}\n환자: {answer}\n{target}, "
                                    "알 수 없으면 ? 한 글자만 출력하세요.").strip()
    except NovaError:
        return "?"  # 모델 호출이 끝내 실패해도 진료는 이어 간다
    return verdict[:1] if verdict[:1] in "+-?" else "?"


def read_exam(client, result: str, findings: list[dict]) -> dict[str, str]:
    """진찰 결과 문장에서 그 진찰로 확인하는 소견들(+/-/?)을 읽는다. 정상 결과는 규칙으로 모두 '-'."""
    if not findings:
        return {}
    text = (result or "").strip()
    marks = re.findall(r"\(([^()]*)\)", text)
    plain_normal = text.rstrip(".") in ("특이 소견 없음", "이상 소견 없음", "정상", "특이사항 없음")
    all_minus = bool(marks) and all(re.fullmatch(r"[\s\-/]+", m) for m in marks)
    # "(+)"가 없고, 괄호 표시가 모두 "(-)"인 결과만 규칙으로 '-'. 수치·서술형 결과는 모델이 읽는다
    if "+" not in text and (plain_normal or all_minus):
        return {f["id"]: "-" for f in findings}
    verdicts = {}
    for f in findings:
        try:
            v = ask_model(client, f"진찰 결과: {text}\n이 결과에 '{f['ko']}' 소견이 있으면 +, 없으면 -, "
                                  "판단할 수 없으면 ? 한 글자만 출력하세요.").strip()[:1]
        except NovaError:
            v = "?"
        verdicts[f["id"]] = v if v in "+-?" else "?"
    return verdicts


REQUIRE_EVIDENCE = True  # 확인된 근거가 없는 후보는 최종 진단으로 고르지 않는다 (eval_kb: +1%p, C03 같은 오진 방지)


def final_choice(ranked: list[dict]) -> dict:
    """최종 진단: 확인된 근거(matched)가 있는 후보 중 1위. 모두 근거가 없으면 원래 1위."""
    if REQUIRE_EVIDENCE:
        for row in ranked:
            if row["matched"]:
                return row
    return ranked[0]


def consult(client, db: MedDB, fallback=None):
    """fallback: KB에 없는 주호소일 때 넘길 consult 함수(예: 시작 패키지의 기본 에이전트)."""
    session = client.session()
    opening, vitals = session["initial"]["opening"], session["initial"]["vital_signs"]
    age, sex = demographics(opening)
    try:
        complaint = pick_complaint(client, db, opening)
    except NovaError:
        complaint = (db.match_complaint(opening) or [{"id": None}])[0]["id"]
    if complaint is None:
        if fallback is not None:
            return fallback(client, None)
        complaint = "fever"  # 대비책이 없으면 가장 넓은 주호소로

    present: list[str] = db.vital_flags(vitals)
    absent: list[str] = []
    asked: set[str] = set()
    answers: dict[str, str] = {}
    # 첫마디에 이미 나온 소견(예: "살이 빠져서", "다이어트를 한 것도 아닌데")은 다시 묻지 않는다
    said = db.match_findings(opening)
    present += [f for f in said["present"] if f not in present]
    absent += [f for f in said["absent"] if f not in present]
    when = re.search(r"[^.]*(?:전부터|동안|개월 전|년 전|주 전|일 전|어제|오늘|아침부터)[^.]*\.?", opening)
    if when and "onset" in db.slots:
        asked.add("onset")                      # 첫마디에 발생 시점이 있으면 다시 묻지 않는다
        answers["onset"] = when.group(0).strip()
    exams_done: set[str] = set()
    exam_results: dict[str, str] = {}
    turns: dict[str, int] = {}
    turn = 0

    def state() -> dict:
        return dict(present=present, absent=absent, asked=asked, exams_done=exams_done, age=age, sex=sex)

    stopped = False
    extra = 0
    while (turn < min(TURN_BUDGET, session["turns_remaining"]) - EXPLAIN_TURNS
           and seconds_left(session) > TIME_MARGIN):
        actions = db.next_actions(complaint, **state())
        required = [a for a in actions if a["stage"] != "discriminate"]
        if required:
            act = required[0]
        else:
            # 필수 단계가 끝나면 상위 후보를 가르는 행동을 몇 개만 더 한다
            more = [a for a in actions if a["stage"] == "discriminate"]
            if not more or extra >= DISCRIMINATE_MAX:
                break
            act = more[0]
            extra += 1
        try:
            if act["type"] == "SAY":
                reply = with_retry(client.say, act["text"])
                turn = reply.get("turn", turn + 1)
                turns[act["target"]] = turn
                asked.add(act["target"])
                if act["target"] in db.slots:
                    answers[act["target"]] = reply["content"]
                else:
                    verdict = read_answer(client, act["text"], reply["content"],
                                          db.findings.get(act["target"], {}).get("ko"))
                    if verdict == "+":
                        present.append(act["target"])
                    elif verdict == "-":
                        absent.append(act["target"])
            else:
                reply = with_retry(client.exam, act["text"])
                turn = reply.get("turn", turn + 1)
                turns[act["target"]] = turn
                exams_done.add(act["target"])
                exam_results[act["target"]] = reply["result"]  # 받은 문장을 그대로 기록한다
                signs = [db.findings[f] for f in act.get("resolves", []) if f in db.findings]
                for fid, verdict in read_exam(client, reply["result"], signs).items():
                    if verdict == "+" and fid not in present:
                        present.append(fid)
                    elif verdict == "-" and fid not in absent:
                        absent.append(fid)
        except NovaError as exc:
            code = getattr(exc, "code", "")
            if act["type"] == "EXAM" and code in ("EXAM_NOT_SPECIFIC", "EXAM_NOT_RECOGNIZED"):
                turn += 1                       # 거절도 1턴을 쓴다(10/11 규칙). 같은 진찰은 다시 보내지 않는다
                exams_done.add(act["target"])
                continue
            stopped = True                      # 턴·시간 소진, 계속된 장애: 지금까지의 기록으로 마무리
            break

    top = final_choice(db.candidates(complaint, present, absent, age, sex, k=5))
    if not stopped:
        for sentence in db.plan(top["id"]).get("explain", [])[:EXPLAIN_TURNS]:
            try:
                with_retry(client.say, sentence)  # 설명은 진료 중 SAY로 해야 대화 평가에 반영된다
            except NovaError:
                break

    record = db.record(complaint, present, absent, answers=answers, turns=turns, vitals=vitals,
                       exam_results=exam_results)
    assessment = db.assessment_plan(complaint, top["id"], present, absent, turns=turns, age=age, sex=sex)
    note, diagnosis = db.build_note(record, assessment)
    return client.diagnose(note=note, diagnosis=diagnosis)


if __name__ == "__main__":
    print(json.dumps(MedDB.empty_note(), ensure_ascii=False, indent=1))
