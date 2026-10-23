"""B1i = B1h + 모의 증례 sol 채점 평(report.md)에서 반복된 지적 수정. 질문 고르기·문진 29턴은 그대로.
  sol이 꼽은 불필요 행동은 대부분 '마무리에서 같은 검사·안심을 되풀이'(심전도로 확인 ×3, 피검사 재안내, 종양 가능성 반복)였고,
  나머지는 포괄적 진찰 요청(EXAM_NOT_SPECIFIC → 결과 없음)이었다. 턴 수와 효율은 거의 무관(B1s 33턴도 14.3).
  1. 마무리·답변에서 이미 말한 검사·계획을 되풀이하는 문장은 말하지 않음(주제어 대조). 새로 할 말이 없으면 답하지 않음.
  2. 설명 지시 보강: 걱정엔 공감 + 그 병이 아닐/맞을 근거('배제 못 해요' 반복 금지), 진단의 뜻에 이 병의 위험(혈전·악순환 등),
     요청엔 이유와 대안, 치료는 방법·진료과 의뢰까지, 위험 신호는 이 병의 응급 증상 2~3개.
  3. 마무리 7 → 8문장, 요청 답을 걱정 확인 계획보다 먼저 남김.
  4. 포괄적 진찰('신경학적 진찰', '복부 진찰', '흉부 진찰')은 구체적 진찰 하나로 바꿔 보냄.
  5. 가임기 여성인데 10턴이 지나도 마지막 생리·임신을 안 물었으면 모델에 참고로 알려 줌 (3건 중 2건에서 '빠진 문진').
  6. 기록: 거절된 진찰을 '환자가 거절'로 적지 않게 알림 문구 수정, 실제로 말하지 않은 교육은 '교육 계획'으로 구분.

B1h = B1g + 리더보드 효율 대응 (질문 고르기·문진 29턴은 그대로).
  근거: B1 효율 샘플 18.68 vs 리더보드 11.51. 샘플 효율은 모든 버전이 18~20이라 차이를 못 보고,
  리더보드 효율은 총 턴(행동 수)을 따라갔다: E7a ~38턴 15~16 · E2care 13.38 · B1 43턴 11.51 · E13 48~50턴 10.00.
  문진을 줄이면 리더보드 정보수집(15.23)을 잃으므로, 정보를 가져오지 않는 턴만 줄인다.
  1. 마무리 설명 10 → 7문장, 설명 중 환자 질문 답 2 → 1회(+중간 확인 뒤 1회) — B1f와 같음. 총 43 → 39~40턴 목표.
  2. 진찰 요청 이름을 온톨로지 표준 진찰 문장으로 바꿔 보냄(무엇을 진찰할지는 모델 선택 그대로) → 거절(EXAM_NOT_RECOGNIZED)로 버리는 턴 감소.
  3. 이미 한 진찰과 같은 진찰은 보내지 않음.
  4. 첫 질문 앞 인사(같은 턴, 30자 안일 때만).

B1g = B1 + 온톨로지 읽기 보강(reader_g) + 구체적인 진단명 유지. 문진·마무리·턴 수는 B1과 같다.
  1~4. examples/reader_g.py: 나열된 부정, 문맥 확인, 일상 표현 보강, 질문+답 함께 읽기.
  5. 진단명: 모델이 쓴 이름이 온톨로지 이름보다 구체적이면(예: 철결핍빈혈 ⊃ 빈혈) 모델 이름으로 제출하고,
     계획(검사·치료·교육)만 온톨로지 질환에서 가져온다 (기존: '빈혈'로 덮어씀 → 진단 5점 척도에서 손해).

B1 = 대회 기본 에이전트의 문진 + 온톨로지 기반 기록 + R1의 마무리 설명.

샘플 검증 10/20~21 (안전 제외 합: 정보·진단·검사·소통·효율)
  E19 (온톨로지 체크리스트 문진 + 온톨로지 기록 + 마무리)  정보 10.63 진단 15.0 검사 7.50 소통 8.28 효율 18.00 → 59.4
  R1b (계획형 문진 + 모델만 기록 + 마무리)                정보 9.65 진단 12.5 검사 6.64 소통 7.78 효율 19.47 → 56.0
  B0  (기본 에이전트: 모델이 매 턴 행동 선택, 온톨로지 없음) 정보 11.91 진단 12.78 검사 0.47 소통 4.78 효율 19.58 → 49.5
→ 문진은 기본 에이전트가 30턴으로 가장 많이 얻었고(정보 11.91), 기록(검사·추적·진단)과 설명(소통)은 온톨로지 쪽이 압도적.
B1은 각 단계에서 가장 잘 나온 것을 이어 붙인다.
 1. 문진·진찰: 기본 에이전트 그대로(모델이 매 턴 다음 행동, 표준 문진 순서). 단, 진단 설명은 하지 않게(마무리에서 함)
    + '한꺼번에 말해 달라' 질문은 보내지 않음(대회 규칙상 거절 = 1턴 손실). 최대 29턴.
 2. 걱정 확인 1턴(기본 에이전트가 묻지 않았으면).
 3. 기록: E-라인의 온톨로지 기록(환자 말에서 소견 표시 → 온톨로지 SOAP 초안·진단 순위·질환 계획 → 모델이 다듬음, 상세 P 지시)
    + 들은 내용 전부 첨부.
 4. 마무리: R1의 설명(질환별 교육·금지 처치·환자 사실 근거, 필수 설명 보장, 걱정 한 번, 중간 확인, 이해 확인).
"""
from __future__ import annotations

import re
import unicodedata

from examples import agent_r1 as R
from examples import hybrid_agent as H
from examples import reader_g as G
from examples.consult_skeleton import NovaError, STOP_CODES, pick_complaint

ASK_TURNS = 29
R.CLOSE_CAP = 8
R.REPLY_CAP = 1
GREET = ("안녕하세요, 담당 의사예요.", "안녕하세요.")
VAGUE_EXAM = re.compile(r"다 해|전부|모두|전신 진찰|신체검진|신체 진찰을|여러")   # 묶은 진찰은 EXAM_NOT_SPECIFIC 거절 = 1턴 손실


def _step(client, session, transcript, turns_left, hint=""):
    import run as BASE                              # 기본 에이전트의 문진 프롬프트·형식 검사를 그대로 쓴다
    request = BASE.situation(session, transcript) + f"\n\n남은 턴: {turns_left + 3}"
    if turns_left <= 8:
        request += "\n문진을 마무리하고 필요한 신체 진찰(EXAM)을 하세요."
    if hint:
        request += "\n" + hint
    request += ("\n진단 설명·마무리 인사는 하지 않습니다(진료 마지막에 따로 함). 질문은 한 가지만, "
                "'모두·전부·자세히 말씀해 주세요'처럼 한꺼번에 알려 달라고 하지 않습니다.\n다음 행동:")
    for _ in range(3):
        step = BASE.parse_json(BASE.ask_doctor(client, BASE.STEP_PROMPT, request, 2048)) or {}
        action = str(step.get("action", "")).upper()
        content = unicodedata.normalize("NFC", str(step.get("content", ""))).strip()
        if action == "DONE" or (action in ("SAY", "EXAM") and 0 < len(content) <= R.MAX_CHARS
                                and not (action == "SAY" and R.ALL_AT_ONCE.search(content))
                                and not (action == "EXAM" and VAGUE_EXAM.search(content))):
            return action, content
        request += f"\n(직전 출력은 형식에 맞지 않았습니다. {R.MAX_CHARS}자 이내, 한 가지만 묻는 JSON 하나만 출력하세요.)"
    return None


GENERIC_EXAM = [(re.compile(r"신경학적|신경 ?진찰|신경계"), "ex_motor"), (re.compile(r"복부 ?진찰|배를? ?진찰|복부를 진찰"), "ex_abd_palp"),
                (re.compile(r"흉부 ?진찰|가슴 ?진찰|폐 ?진찰"), "ex_lung_ausc"), (re.compile(r"심장 ?진찰"), "ex_heart_ausc")]


def _hint(v) -> str:
    if v.sex == "F" and v.age and 12 <= v.age <= 55 and v.turn >= 10 \
            and not any(re.search(r"생리|월경|임신", q) for q in v.asked):
        return "[참고] 가임기 여성인데 아직 마지막 생리·임신 가능성을 확인하지 않았습니다(필요하면 한 가지씩)."
    return ""


def _run(v: R.Visit, client, db):
    try:
        v.complaint = pick_complaint(client, db, v.opening)
    except Exception:  # noqa: BLE001
        v.complaint = None
    G.install(db)
    kb = H.Tracker(db, v.complaint, v.age, v.sex, v.opening, v.vitals, "clinical", "reviewed")
    kb.note_seen(v.opening, 0)
    transcript: list[str] = []
    # 1. 문진·진찰 (기본 에이전트)
    fails = 0
    while not v.stopped and v.turn < ASK_TURNS and v.left() > R.TIME_MARGIN and fails < 3:
        try:
            step = _step(client, v.session, transcript, ASK_TURNS - v.turn, _hint(v))
        except NovaError:
            break
        if step is None:
            fails += 1
            continue
        if step[0] == "DONE":
            break
        action, content = step
        if action == "SAY":
            if not v.asked:                                  # 첫 질문: 인사를 같은 턴에 (질문 내용은 그대로)
                for g in GREET:
                    if R.fits(f"{g} {content}") and not content.startswith("안녕"):
                        content = f"{g} {content}"
                        break
            if any(R.bigram_sim(content, q) >= 0.8 for q in v.asked):
                transcript.append(f"(이미 한 질문이라 생략함: {content} — 아직 묻지 않은 것을 물으세요)")
                fails += 1
                continue
            a = v.say(content, "base")
            if a is None:
                fails += 1
                continue
            transcript += [f"의사: {content}", f"환자: {a}"]
            kb.note_seen(a, v.turn)
            G.read_qa(kb, db, content, a, v.turn)
            if re.search(R.CONCERN_Q[:6], content) or re.search(r"걱정", content):
                v.concern = v.concern or a
        else:
            eid0 = kb.exam_id(content)
            if not eid0:
                for pat, gid in GENERIC_EXAM:                # 포괄적 진찰 → 구체적 진찰 하나 (EXAM_NOT_SPECIFIC 방지)
                    if pat.search(content) and gid in db.exams and gid not in kb.exams_done:
                        eid0 = gid
                        break
            if eid0 and eid0 in db.exams and R.fits(db.exams[eid0]["action"]):
                content = db.exams[eid0]["action"]           # 온톨로지 표준 진찰 문장 (거절 = 1턴 손실 방지)
            if any(content == n for n, _ in v.exams) or (eid0 and eid0 in kb.exams_done):
                transcript.append(f"(이미 한 진찰이라 생략함: {content} — 다른 진찰이나 질문을 하세요)")
                fails += 1
                continue
            before = v.turn
            res = v.exam(content)
            if res is None:
                transcript.append(f"(시스템 알림: '{content}' 진찰 요청이 구체적이지 않아 실행되지 않음, 결과 없음. 환자가 거절한 것이 아님. 구체적인 진찰 동작 하나로)")
                fails += 1 if v.turn == before else 0
                continue
            transcript.append(f"진찰({content}): {res}")
            eid = kb.exam_id(content)
            if eid:
                kb.exams_done.add(eid)
                kb.exam_results[eid] = res
        fails = 0
    # 2. 걱정 확인
    if not v.concern and v.room(14):
        a = v.say(R.CONCERN_Q, "concern")
        if a:
            transcript += [f"의사: {R.CONCERN_Q}", f"환자: {a}"]
            if not re.match(r"^(아니|없|특별히 없|딱히)", a):
                v.concern = a
    # 3. 기록 (온톨로지 초안 + 모델)
    note, dx = H.write_record(client, db, kb, v.opening, v.vitals, transcript, contextual_plan=True)
    for sec, fields in R.RECORD_FIELDS.items():
        for f in fields:
            note[sec][f] = str(note[sec].get(f, "") or "")
    pos, neg = [], []
    for x in v.qa:
        if R.REFUSE.search(x["a"]) or x["tag"] == "concern":
            continue
        (neg if R.is_neg(x["a"]) else pos).append(f"{x['q'].rstrip('?')} → {x['a']}")
    if pos:
        note["S"]["hpi"] = (note["S"]["hpi"].rstrip() + "\n[문진에서 환자가 말한 내용] " + " / ".join(pos)).strip()
    if neg:
        note["S"]["ros"] = (note["S"]["ros"].rstrip() + "\n[문진에서 없다고 한 것] " + " / ".join(neg)).strip()
    if v.concern:
        note["S"]["hpi"] += "\n환자의 걱정·요청: " + v.concern
    # 4. 마무리 설명 (R1)
    said = v.closing(note, dx)
    lines = note["P"]["education"].strip().splitlines()
    teachback = [x for x in lines if x.startswith("이해 확인 답변")]
    plan_edu = "\n".join(x for x in lines if not x.startswith("이해 확인 답변")).strip()
    note["P"]["education"] = ((("교육 계획(다음 진료에서 설명): " + plan_edu + "\n") if plan_edu else "")
                              + "오늘 환자에게 실제로 설명함: " + " / ".join(said)
                              + ("\n" + "\n".join(teachback) if teachback else "")).strip()
    v.submit(note, dx)


def consult(client, db, fallback=None, **_):
    v = R.Visit(client, db)
    v.submitted = False
    try:
        _run(v, client, db)
    except Exception:  # noqa: BLE001 — 어떤 오류에서도 반드시 제출
        if not v.submitted:
            try:
                note, dx = v.write_record()
            except Exception:  # noqa: BLE001
                note, dx = R.empty_record(), "진단 미정"
            try:
                v.submit(note, dx)
            except Exception:  # noqa: BLE001
                pass
