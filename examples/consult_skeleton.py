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

from meddb import MedDB

TURN_BUDGET = 24        # 필수 단계가 14~22턴이므로 설명 2턴을 더해도 한도 50턴에 여유가 있다
EXPLAIN_TURNS = 2
YES = ("네", "예", "맞아", "있어", "있습", "그래", "그렇")
NO = ("아니", "없어", "없습", "없는", "안 ", "전혀")


def prepare():
    """증례에 접근하기 전에 한 번 불린다. 파일을 쓰지 않으므로 읽기 전용 환경에서도 열린다."""
    return MedDB.open()


def demographics(opening: str) -> tuple[int | None, str | None]:
    age = re.search(r"(\d{1,3})\s*(?:세|살)", opening)
    sex = "M" if re.search(r"남자|남성|남\b", opening) else "F" if re.search(r"여자|여성|여\b", opening) else None
    return (int(age.group(1)) if age else None), sex


def ask_model(client, prompt: str, max_tokens: int = 1024) -> str:
    reply = client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    return reply["choices"][0]["message"]["content"] or ""


def pick_complaint(client, db: MedDB, opening: str) -> str | None:
    """표현 사전으로 못 찾으면 모델에게 고르게 한다. 예선은 증례마다 모델 호출이 1회 이상 있어야 하므로
    사전으로 찾았더라도 확인을 겸해 한 번 묻는다. KB에 맞는 주호소가 없으면 None."""
    hits = db.match_complaint(opening)
    options = ", ".join(f"{c['id']}({c['ko']})" for c in db.complaints.values())
    answer = ask_model(client, f"환자의 첫마디: {opening}\n주호소를 다음 중 하나의 id로만 답하세요. "
                               f"맞는 것이 없으면 none: {options}")
    chosen = next((cid for cid in db.complaints if cid in answer), None)
    return hits[0]["id"] if hits else chosen


def read_answer(client, question: str, answer: str) -> str:
    """환자 답을 '+'(있음), '-'(없음), '?'(알 수 없음)로 읽는다. 뻔한 답은 규칙으로, 나머지는 모델로."""
    head = answer.strip()[:6]
    if any(head.startswith(w) or w in head for w in NO):
        return "-"
    if any(head.startswith(w) for w in YES):
        return "+"
    verdict = ask_model(client, f"의사: {question}\n환자: {answer}\n환자의 답이 '있다'면 +, '없다'면 -, "
                                "알 수 없으면 ? 한 글자만 출력하세요.", max_tokens=512).strip()
    return verdict[:1] if verdict[:1] in "+-?" else "?"


def consult(client, db: MedDB, fallback=None):
    """fallback: KB에 없는 주호소일 때 넘길 consult 함수(예: 시작 패키지의 기본 에이전트)."""
    session = client.session()
    opening, vitals = session["initial"]["opening"], session["initial"]["vital_signs"]
    age, sex = demographics(opening)
    complaint = pick_complaint(client, db, opening)
    if complaint is None:
        if fallback is not None:
            return fallback(client, None)
        complaint = "fever"  # 대비책이 없으면 가장 넓은 주호소로

    present: list[str] = db.vital_flags(vitals)
    absent: list[str] = []
    asked: set[str] = set()
    exams_done: set[str] = set()
    answers: dict[str, str] = {}
    exam_results: dict[str, str] = {}
    turns: dict[str, int] = {}
    turn = 0

    def state() -> dict:
        return dict(present=present, absent=absent, asked=asked, exams_done=exams_done, age=age, sex=sex)

    while turn < min(TURN_BUDGET, session["turns_remaining"]) - EXPLAIN_TURNS:
        actions = db.next_actions(complaint, **state())
        required = [a for a in actions if a["stage"] != "discriminate"]
        if not required:
            break  # 필수 단계가 끝났다. 감별 질문을 더 할지는 코어 에이전트가 정한다.
        act = required[0]
        if act["type"] == "SAY":
            reply = client.say(act["text"])
            turn += 1
            turns[act["target"]] = turn
            asked.add(act["target"])
            if act["target"] in db.slots:
                answers[act["target"]] = reply["content"]
            else:
                verdict = read_answer(client, act["text"], reply["content"])
                if verdict == "+":
                    present.append(act["target"])
                elif verdict == "-":
                    absent.append(act["target"])
        else:
            reply = client.exam(act["text"])  # EXAM_NOT_SPECIFIC·EXAM_NOT_RECOGNIZED 처리는 코어 쪽에서
            turn += 1
            turns[act["target"]] = turn
            exams_done.add(act["target"])
            exam_results[act["target"]] = reply["result"]  # 받은 문장을 그대로 기록한다

    top = db.candidates(complaint, present, absent, age, sex, k=1)[0]
    for sentence in db.plan(top["id"]).get("explain", [])[:EXPLAIN_TURNS]:
        client.say(sentence)  # 설명은 기록이 아니라 진료 중 SAY로 해야 대화 평가에 반영된다

    record = db.record(complaint, present, absent, answers=answers, turns=turns, vitals=vitals,
                       exam_results=exam_results)
    assessment = db.assessment_plan(complaint, top["id"], present, absent, turns=turns, age=age, sex=sex)
    note, diagnosis = db.build_note(record, assessment)
    return client.diagnose(note=note, diagnosis=diagnosis)


if __name__ == "__main__":
    print(json.dumps(MedDB.empty_note(), ensure_ascii=False, indent=1))
