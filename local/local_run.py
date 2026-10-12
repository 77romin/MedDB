"""대회 서버 없이 내 PC에서 진료 한 건을 돌려 본다 (표준 라이브러리만).

  Doctor 모델   : Ollama의 gpt-oss:20b (대회와 같은 모델)
  가상 환자     : 같은 모델로 대신함 (대회는 비공개 모델 + 비공개 대본)
  진찰 판정     : 같은 모델이 증례의 진찰표에서 고름 (거절도 1턴, 대회 규칙과 같게)
  채점          : 하지 않음. 대화 기록과 제출 기록만 보여 준다.

사용법 (nova-starter 폴더 안에서, Ollama가 켜진 상태로):
  python local/local_run.py --case local/cases/C01_insomnia.json --agent baseline
  python local/local_run.py --case local/cases/C01_insomnia.json --agent meddb

--agent baseline : 시작 패키지의 run.py (기본 에이전트)
--agent meddb    : examples/consult_skeleton.py (온톨로지 사용, KB 밖 주호소면 기본 에이전트로 넘김)
결과는 local/out/<증례>_<agent>.json 에도 저장한다.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT)]

OLLAMA = "http://localhost:11434/v1/chat/completions"
MODEL = "gpt-oss:20b"
MAX_TURNS = 50

PATIENT_RULES = """당신은 병원에 온 환자입니다. 아래 [환자 정보]만 근거로 답하세요.
1. 의사가 물어본 것에만 답합니다. 묻지 않은 정보는 먼저 말하지 않습니다.
2. 일반인 말투로 20자 안팎, 한 문장으로 답합니다. 의학 용어나 진단명은 쓰지 않습니다.
3. [환자 정보]에 없는 증상은 "그런 건 없었어요", 기억할 만한 것이 아니면 "잘 모르겠어요"라고 답합니다.
4. 질문이 여러 개거나 뭉뚱그려 물으면 "한 번에 하나씩 물어봐 주세요."라고 답합니다.
5. 설명이나 공감에는 환자답게 짧게 반응합니다.
답만 출력하세요."""

EXAM_RULES = """당신은 진찰 판정자입니다. 의사의 요청을 보고 아래 중 하나만 JSON으로 출력하세요.
- 진찰표의 항목 하나에 해당: {"verdict":"row","name":"항목 이름"}
- 실제 신체진찰 동작 하나지만 진찰표에 없음: {"verdict":"unlisted","name":"진찰 이름"}
- 여러 진찰을 묶었거나 방법이 여러 가지라 특정할 수 없음: {"verdict":"too_broad"}
- 신체진찰이 아님(문진, 혈액·영상 검사, 처치, 기록 등): {"verdict":"not_exam"}"""


class LocalError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def ollama(messages, max_tokens=2048, reasoning_effort="medium", temperature=None):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "reasoning_effort": reasoning_effort}
    if temperature is not None:
        body["temperature"] = temperature
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def parse_json(text):
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


class LocalClient:
    """nova_sdk.Client와 같은 메서드·응답 모양. 서버 대신 Ollama와 증례 파일을 쓴다."""

    def __init__(self, case):
        self.case = case
        self.turn = 0
        self.dialog = []          # 가상 환자에게 보여 줄 지금까지의 대화
        self.log = []             # 화면·파일로 남길 행동 기록
        self.calls = {"doctor": 0, "patient": 0, "examiner": 0}
        self.tokens = {"in": 0, "out": 0}
        self.submitted = None
        self.started = time.time()

    # --- 대회 SDK와 같은 이름 ---------------------------------------------------
    def session(self):
        return {"initial": {"opening": self.case["opening"], "vital_signs": self.case["vital_signs"]},
                "turns_remaining": MAX_TURNS - self.turn, "deadline": None}

    def chat(self, messages, *, max_tokens=2048, request_id=None, reasoning_effort="medium", temperature=None):
        self.calls["doctor"] += 1
        reply = ollama(messages, max_tokens, reasoning_effort, temperature)
        usage = reply.get("usage") or {}
        self.tokens["in"] += usage.get("prompt_tokens", 0)
        self.tokens["out"] += usage.get("completion_tokens", 0)
        if not (reply["choices"][0]["message"].get("content") or "").strip():
            self.log.append({"kind": "note", "text": "Doctor 빈 답 (대회에서는 PROVIDER_RESPONSE_INVALID)"})
        return reply

    def say(self, content, *, request_id=None):
        text = self._check(content)
        self._use_turn()
        self.calls["patient"] += 1
        info = "\n".join("- " + f for f in self.case["facts"])
        history = "\n".join(self.dialog[-30:])
        reply = ollama([{"role": "system", "content": PATIENT_RULES + "\n\n[환자 정보]\n" + self.case["opening"] + "\n" + info},
                        {"role": "user", "content": (history + "\n" if history else "") + "의사: " + text + "\n환자:"}],
                       max_tokens=1024, reasoning_effort="low")
        answer = (reply["choices"][0]["message"].get("content") or "").strip().strip('"') or "잘 모르겠어요."
        self.dialog += ["의사: " + text, "환자: " + answer]
        self.log.append({"turn": self.turn, "kind": "SAY", "text": text, "result": answer})
        return {"status": "OK", "content": answer, "turn": self.turn, "turns_remaining": MAX_TURNS - self.turn}

    def exam(self, content, *, request_id=None):
        text = self._check(content)
        self._use_turn()  # 대회 규칙(10/11~): 거절된 진찰도 1턴을 쓴다
        self.calls["examiner"] += 1
        table = "\n".join("- " + k for k in self.case["exams"])
        reply = ollama([{"role": "system", "content": EXAM_RULES},
                        {"role": "user", "content": f"[진찰표]\n{table}\n\n[의사의 요청]\n{text}"}],
                       max_tokens=1024, reasoning_effort="low")
        verdict = parse_json(reply["choices"][0]["message"].get("content")) or {}
        kind = verdict.get("verdict")
        if kind == "row" and verdict.get("name") in self.case["exams"]:
            result = self.case["exams"][verdict["name"]]
        elif kind in ("row", "unlisted"):
            result = self.case.get("default_exam", "특이 소견 없음")
        else:
            code = "EXAM_NOT_RECOGNIZED" if kind == "not_exam" else "EXAM_NOT_SPECIFIC"
            self.log.append({"turn": self.turn, "kind": "EXAM", "text": text, "result": code})
            raise LocalError(code)
        self.log.append({"turn": self.turn, "kind": "EXAM", "text": text, "result": result, "verdict": kind})
        return {"status": "OK", "result": result, "turn": self.turn, "turns_remaining": MAX_TURNS - self.turn}

    def diagnose(self, *, note, diagnosis, request_id=None):
        self.submitted = {"diagnosis": diagnosis, "note": note}
        return {"status": "completed", "turn": self.turn}

    # --- 내부 ------------------------------------------------------------------
    def _check(self, content):
        text = unicodedata.normalize("NFC", str(content))
        if not text or len(text) > 30:
            raise ValueError("SAY, EXAM and TEST require 1–30 NFC characters")
        return text

    def _use_turn(self):
        if self.turn >= MAX_TURNS:
            raise LocalError("TURN_LIMIT_REACHED")
        self.turn += 1


def load_agent(name):
    import nova_sdk
    nova_sdk.NovaError = LocalError  # 기본 에이전트의 오류 처리가 로컬 오류도 받도록
    import run as baseline
    baseline.NovaError = LocalError
    if name == "baseline":
        return baseline.prepare, baseline.consult
    from examples.consult_skeleton import consult, prepare
    return prepare, (lambda client, db: consult(client, db, fallback=baseline.consult))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--agent", choices=["baseline", "meddb"], default="baseline")
    args = ap.parse_args()
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    prepare, consult = load_agent(args.agent)
    client = LocalClient(case)
    state = prepare()
    print(f"[{case['id']}] {args.agent} 시작 — Doctor·환자·진찰 판정 모두 {MODEL}\n")
    try:
        consult(client, state)
    except Exception as exc:  # 에이전트가 터져도 지금까지의 기록은 보여 준다
        print(f"\n!! 에이전트 오류: {type(exc).__name__}: {exc}\n")
    for row in client.log:
        if row["kind"] == "note":
            print("   (" + row["text"] + ")")
        else:
            print(f"턴 {row['turn']:>2} {row['kind']:<4} {row['text']}  →  {row['result']}")
    sec = time.time() - client.started
    print(f"\n턴 {client.turn} · 호출 {client.calls} · Doctor 토큰 입력 {client.tokens['in']} 출력 {client.tokens['out']} · {sec:.0f}초")
    if client.submitted:
        print(f"\n제출 주진단: {client.submitted['diagnosis']}   (증례 정답: {case['answer']['diagnosis']})")
        for section, fields in client.submitted["note"].items():
            for field, text in fields.items():
                print(f"[{section}.{field}] " + (text.replace(chr(10), " | ") if text else "(빈칸)"))
    else:
        print("\n!! 기록을 제출하지 못함 (대회에서는 0점)")
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    path = out / f"{case['id']}_{args.agent}.json"
    path.write_text(json.dumps({"case": case["id"], "agent": args.agent, "turns": client.turn, "calls": client.calls,
                                "tokens": client.tokens, "seconds": round(sec), "log": client.log,
                                "submitted": client.submitted}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {path}")


if __name__ == "__main__":
    main()
