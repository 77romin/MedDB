"""R1b — R1 + SOAP에 온톨로지 재연결(유력 진단의 표준 계획을 기록 모델에 주고, 비운 A·P 칸은 온톨로지로 채움).

R1 — 처음부터 다시 짠 진료 에이전트: '계획형 · 진단 중심'.

E1~E19는 주호소별 질문 목록을 우선순위대로 묻고, 문제가 보일 때마다 규칙을 덧붙이는 방식이었다.
리더보드는 버전과 상관없이 64~68점, 정보수집 10~13/25에 머물렀다.
sol 채점의 '빠진 필요 문진'은 거의 모두 **진단에 딸린 항목**이었다
(약물과용두통: 진통제 하루 최대량·성분, 심방세동: 뇌졸중 위험인자·수면무호흡, 철결핍빈혈: 얼음 갈망·다른 출혈원).
모범 기록은 '이 진단을 내리고 치료하려면 무엇을 확인했어야 하는가'로 짜여 있는데, 우리는 주호소 목록만 묻고 있었다.

R1의 흐름 (모델 호출 약 15~25회, E19의 절반 이하)
 1. 접수(규칙, ~8턴): 인사 → 주호소 핵심(시작·양상·경과) → 걱정 → 이 주호소의 위험 신호
 2. 계획(모델 1회): 지금까지 들은 것으로 유력 진단 3개를 세우고, 남은 턴에 물을 질문(진단 확인·중증도·
    치료 결정에 필요한 위험인자·감별)과 '있다'고 하면 이어 물을 질문, 할 진찰, 중간 요약 문장을 한 번에 만든다.
    온톨로지(주호소 프로토콜·질환 후보·진찰 이름)를 메뉴로 주고, 규칙으로 검사한다(30자·한 가지만·이미 들은 것 금지).
 3. 실행(규칙 + 필요할 때만 모델): 계획대로 묻는다. '없다'고 하면 그 질문에 딸린 꼬리 질문은 묻지 않는다.
    의미 있는 답 뒤에만 짧은 호응과 '이미 들은 질문'을 모델이 고른다(인용 근거가 실제 대화에 있을 때만 건너뜀).
 4. 중간 요약 1턴 → 진찰 → 기본 병력 중 빠진 것
 5. 기록(모델 1회 + 규칙): 대회 기록 형식 + 대화에서 들은 것(있다·없다)과 진찰 결과를 빠짐없이 붙임
 6. 마무리(모델 1회 + 규칙): 진단의 뜻·원인·걱정(근거+확인 계획)·요청·검사·치료·위험 신호·재진·중간 확인·
    선택지·생활 교육. 온톨로지의 질환별 치료·교육·금지 처치와 환자 본인의 사실을 근거로. 필수 설명은 코드로 보장.
    환자 질문엔 바로 답(2회 + 중간 확인 뒤 1회), 같은 걱정은 다시 안심하지 않음 → 이해 확인 → 제출.
 대회 규칙: SAY·EXAM 30자, 50턴, 30분, 묶음·한꺼번에 질문 금지(거절 = 1턴 손실), 모든 예외에서도 반드시 제출.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

from nova_sdk import RECORD_FIELDS, NovaError, empty_record
from examples.consult_skeleton import STOP_CODES, demographics, pick_complaint, seconds_left, with_retry

DATA = Path(__file__).resolve().parent.parent / "meddb" / "data"
PROTO = json.loads((DATA / "protocols.json").read_text(encoding="utf-8"))["complaints"]
SPLIT = json.loads((DATA / "ask_split.json").read_text(encoding="utf-8"))

MAX_CHARS = 30
ASK_CAP = 30            # 질문·요약·진찰 턴 상한 (리더보드 효율: 32턴 15~16점, 37턴+긴 마무리 10점)
CLOSE_CAP = 10          # 마무리 설명 문장 상한 (중간 확인 포함) → 전체 최대 45턴, 보통 41~43턴
REPLY_CAP = 2           # 설명 도중 환자 질문에 답하는 횟수 (+ 중간 확인 뒤 1회)
TIME_MARGIN = 420       # 질문 단계를 끝낼 남은 시간(초): 느린 서버에서도 기록·마무리를 끝낼 여유
LEAN_AT = 900           # 남은 시간이 이보다 적으면 선택적 모델 호출(호응·계획 보강)을 끈다
GREETING = "안녕하세요, 담당 의사예요. 어디가 불편하세요?"
CONCERN_Q = "가장 걱정되시는 점은 무엇인가요?"
CHECK_Q = "여기까지 궁금한 점 있으세요?"
TEACH_Q = "집에서 어떻게 하실지 말씀해 주시겠어요?"

NEG = re.compile(r"^(아니|없어|없습|그런 건 없|그런 적 없|안 |전혀|거의 안)|(없어요|없었어요|않아요|않았어요|안 해요|안 마셔요|안 피워요|안 먹어요)\.?$")
UNSURE = re.compile(r"모르겠|잘 모르|기억이 안|글쎄")
REFUSE = re.compile(r"하나씩")
COMPOUND = re.compile(r"(이나|거나|또는|및|이랑|하고)\s|,|·|/")
ALL_AT_ONCE = re.compile(r"모두|전부|한꺼번에|다 말씀|빠짐없이|자세히 말씀|처음.{0,8}부터.{0,6}지금까지|있는 대로")
DRUG = re.compile(r"\d+\s*(mg|밀리|알|정|캡슐)|복용하세요")
ASK_CUE = re.compile(r"\?|궁금|걱정|겁|무서|불안|아닌가요|아닌지|되나요|될까요|해야|하나요|있나요|인가요|싶어요|괜찮을까")
ACK_PATIENT = re.compile(r"^\s*(네|예)[,.]?\s*(알겠어요|알겠습니다)?[.,]?\s*")
REQUEST_CUE = re.compile(r"원해|원하|싶어|해 주|받고|처방|찍어|주사|약만|빨리")
URGENT = re.compile(r"응급|입원|당일|즉시|119|오늘 바로")
SAFETY = re.compile(r"응급실|119|바로 오|바로 병원")
TIME_SAID = re.compile(r"(\d+|한|두|세|네|몇|며칠|일주일|보름|한 달|석 달|넉 달|여러)\s*(일|주|달|개월|년|해|시간)\s*(째|전|동안|전부터)|새벽부터|어제부터|오늘 아침|그저께|지난주|지난달")
PARTICLE = re.compile(r"(이나|이랑|에서|으로|이|가|을|를|은|는|에|도|과|와|랑|로|의|만)$")
VERB_END = re.compile(r"(요|까|니|세요|셨|습니다|어도|아도|고|면|게|지|죠|나|가|해)$")
GENERIC = {"증상", "적", "때", "최근", "요즘", "혹시", "가장", "평소", "지금", "그", "이", "몇", "얼마나", "언제", "어디",
           "하루", "한", "번", "점", "느낌", "무엇", "어떤", "다른", "처음", "자주", "많이", "조금", "특별히", "오늘",
           "있어", "없어", "드시", "받아", "보셨", "생긴", "때문", "일상생활", "생활"}
ONE_CHAR = {"숨", "열", "피", "땀", "코", "귀", "눈", "목", "배", "약", "술", "빛", "턱", "혀", "변"}
COMMON_EXAMS = ["ex_heart_ausc", "ex_lung_ausc", "ex_abd_palp", "ex_neuro_motor", "ex_cranial", "ex_pupil",
                "ex_throat", "ex_neck_nodes", "ex_thyroid", "ex_skin", "ex_leg_edema", "ex_jvp"]


def nfc(t) -> str:
    return unicodedata.normalize("NFC", str(t or "")).strip()


def fits(t) -> bool:
    return 0 < len(nfc(t)) <= MAX_CHARS


def is_neg(a: str) -> bool:
    a = nfc(a)
    first = re.split(r"[,.]", a)[0]
    return not re.match(r"^\s*(네|예)", a) and bool(NEG.search(first) or NEG.search(a))


def parse_json(text):
    dec = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                v, _ = dec.raw_decode(text, i)
                if isinstance(v, dict):
                    return v
            except ValueError:
                continue
    return None


def nouns(text: str) -> list[str]:
    out = []
    for tok in re.split(r"[\s,·/]+", re.sub(r"[?.!]", "", text or "")):
        stem = PARTICLE.sub("", tok)
        if not tok or (stem == tok and VERB_END.search(tok) and len(tok) > 1):
            continue
        if not stem or stem in GENERIC or (len(stem) == 1 and stem not in ONE_CHAR):
            continue
        out.append(stem)
    return out


def bigram_sim(a: str, b: str) -> float:
    a, b = re.sub(r"[^가-힣0-9]", "", a or ""), re.sub(r"[^가-힣0-9]", "", b or "")
    ga, gb = {a[i:i + 2] for i in range(len(a) - 1)}, {b[i:i + 2] for i in range(len(b) - 1)}
    return len(ga & gb) / max(1, len(ga | gb)) if ga and gb else 0.0



def repeats(s: str, said: list) -> bool:
    """새 내용 없이 이미 말한 것을 되풀이하는 문장인지: 핵심 명사가 모두 앞 설명에 이미 나왔으면 되풀이로 본다.
    (sol 채점의 '불필요 행동' 대부분: '심전도로 확인하겠습니다' ×3, '피검사를 할게요' 재안내, 종양 가능성 반복)"""
    if not said:
        return False
    if max(bigram_sim(s, x) for x in said) >= 0.6:
        return True
    ns = nouns(s)
    text = re.sub(r"\s", "", " ".join(said))
    return bool(ns) and all(n in text for n in ns)


# =====================================================================================================
class Visit:
    def __init__(self, client, db):
        self.client, self.db = client, db
        self.session = with_retry(client.session)
        init = self.session.get("initial", {})
        self.opening, self.vitals = nfc(init.get("opening", "")), str(init.get("vital_signs", ""))
        self.age, self.sex = demographics(self.opening)
        self.complaint = None
        self.turn, self.stopped = 0, False
        self.qa: list[dict] = []          # {"q","a","tag","kind"}
        self.exams: list[tuple[str, str]] = []
        self.asked: list[str] = []
        self.concern = ""
        self.acks: list[str] = []
        self.dx: list[dict] = []
        self.summary = ""
        self.calls = 0

    # ---- 시간·턴 ------------------------------------------------------------------------------------
    def left(self) -> float:
        return seconds_left(self.session)

    def room(self, n=1) -> bool:
        return not self.stopped and self.turn + n <= 50 and self.left() > 60

    def chat(self, system, user, max_tokens=2048, optional=False) -> str:
        if optional and self.left() < LEAN_AT:
            return ""
        self.calls += 1
        try:
            r = with_retry(self.client.chat, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                           max_tokens=max_tokens)
            return r["choices"][0]["message"]["content"] or ""
        except NovaError:
            return ""

    # ---- 행동 ---------------------------------------------------------------------------------------
    def say(self, text, tag="", kind="ask"):
        text = nfc(text)
        if not fits(text) or not self.room():
            return None
        try:
            r = with_retry(self.client.say, text)
        except NovaError as e:
            if getattr(e, "code", "") in STOP_CODES:
                self.stopped = True
            return None
        self.turn = r.get("turn", self.turn + 1)
        ans = nfc(r.get("content", ""))
        self.qa.append({"q": text, "a": ans, "tag": tag, "kind": kind})
        if kind == "ask":
            self.asked.append(text)
        return ans

    def exam(self, text):
        if not fits(text) or not self.room():
            return None
        try:
            r = with_retry(self.client.exam, text)
        except NovaError as e:
            code = getattr(e, "code", "")
            if code in STOP_CODES:
                self.stopped = True
            elif code in ("EXAM_NOT_RECOGNIZED", "EXAM_NOT_SPECIFIC"):
                self.turn += 1                     # 거절된 진찰도 1턴
            return None
        self.turn = r.get("turn", self.turn + 1)
        self.exams.append((text, nfc(r.get("result", ""))))
        return r.get("result")

    # ---- 기억 ---------------------------------------------------------------------------------------
    def heard(self) -> list[str]:
        return [self.opening] + [x["a"] for x in self.qa]

    def known(self, q: str) -> bool:
        """같은(비슷한) 질문을 이미 했거나, 질문의 핵심 명사가 모두 앞 답에 나왔으면 묻지 않는다."""
        if any(bigram_sim(q, p) >= 0.6 for p in self.asked):
            return True
        if re.search(r"몇|얼마나|언제|며칠|어디서", q):
            return False                           # 양·시점 질문은 명사가 같아도 답이 아님
        ns = nouns(q)
        if not ns:
            return False
        for a in self.heard():
            hit = sum(1 for n in ns if (re.search(re.escape(n) + r"(이|은|을|도|가|과|는)", a) if len(n) == 1 else n in a))
            if hit == len(ns) and len(ns) >= 1 and not (len(ns) == 1 and len(ns[0]) == 1 and ns[0] not in a):
                return True
        return False

    def valid_q(self, q: str) -> bool:
        q = nfc(q)
        return (fits(q) and q.endswith("?") and q.count("?") == 1 and not COMPOUND.search(q)
                and not ALL_AT_ONCE.search(q) and not self.known(q))

    # ==============================================================================================
    def run(self):
        try:
            self.complaint = pick_complaint(self.client, self.db, self.opening)
        except Exception:  # noqa: BLE001
            self.complaint = None
        self.intake()
        plan = self.make_plan()
        self.execute(plan)
        note, dx = self.write_record()
        said = self.closing(note, dx)
        note["P"]["education"] = (note["P"]["education"].rstrip() + "\n환자에게 설명함: " + " / ".join(said)).strip()
        self.submit(note, dx)

    # ---- 1. 접수 -------------------------------------------------------------------------------------
    def intake(self):
        self.say(GREETING, "greet", kind="open")
        proto = PROTO.get(self.complaint or "default") or {}
        items = self.db.items.get(self.complaint, {}) if self.complaint else {}
        slots = [s for s in (items.get("slot") or ["onset", "course"]) if s in self.db.slots and s != "parent_height"]
        qs = []
        for s in (["onset"] + [x for x in slots if x != "onset"])[:3]:
            qs.append((self.db.slots[s]["ask"], "slot:" + s))
        qs.append((CONCERN_Q, "concern"))
        try:
            flags = self.db.red_flags_pending(self.complaint, (), (), (), self.age, self.sex) if self.complaint else []
        except Exception:  # noqa: BLE001
            flags = []
        for fl in flags:
            for fid in fl["unchecked"][:2]:
                act = self.db._action(fid, "core", "red flag")
                if act and act["type"] == "SAY":
                    qs.append((act["text"], "flag:" + fid))
        seen = set()
        for q, tag in qs[:9]:
            if q in seen or not self.room() or self.turn >= 9:
                continue
            seen.add(q)
            if tag != "concern" and COMPOUND.search(q):
                fid = tag.split(":", 1)[1] if ":" in tag else ""
                q = SPLIT.get(fid, [""])[0]           # 묶음 질문은 한 가지만 (거절 = 1턴 손실)
                if not q:
                    continue
            if tag != "concern" and self.known(q):
                continue
            if tag == "slot:onset" and TIME_SAID.search(self.opening):
                continue                               # 시작 진술에 이미 시점이 있음
            a = self.say(q, tag)
            if tag == "concern" and a and not re.match(r"^(아니|없|특별히 없|딱히)", a):
                self.concern = a
            if a and REFUSE.search(a):
                continue

    # ---- 2. 계획 -------------------------------------------------------------------------------------
    PLAN_SYSTEM = """당신은 외래 초진 의사의 [진료 계획]을 세웁니다. 지금까지의 문진을 읽고 남은 문진·진찰을 계획합니다.
채점은 '모범 초진 기록'과 비교해 필요한 문진·진찰을 했는지 봅니다. 모범 기록은 '이 진단을 내리고 치료를 정하려면 무엇을 확인해야 하는가'로 짜여 있습니다.
가상 환자 규칙: 물은 것에만 짧게 답합니다. 두 가지를 묶어 묻거나('A이나 B', 'A거나 B', 쉼표) 한꺼번에 말해 달라면 거절합니다.

순서대로 생각합니다.
1. dx: 유력 진단 3개(가장 유력한 것부터, 원인·유형까지 구체적으로)와 근거.
2. questions: 남은 문진 최대 18개. 우선순위:
   (1) 1순위 진단을 확인하는 핵심 소견과 중증도·양(빈도·기간·하루 최대량 등)
   (2) 치료·처치 결정에 필요한 것(위험인자, 동반 질환, 복용 약·성분, 알레르기, 임신 가능성, 유발 요인)
   (3) 2·3순위 진단을 가르는 소견
   (4) 기본 병력 중 아직 안 들은 것: 지병, 복용 약, 약 알레르기, 가족력, 흡연, 음주, 직업·생활
   각 질문은 한 가지만, 공백 포함 30자 이내, 쉬운 존댓말, 물음표 하나. 이미 들은 내용은 묻지 않습니다.
   if_yes: 환자가 '있다'고 답하면 이어서 물을 구체화 질문(양·횟수·시점·종류) 최대 2개. '없다'면 묻지 않습니다.
3. exams: [진찰 메뉴]에서 이 진단들에 필요한 진찰 4~7개를 이름 그대로.
4. summary: 진찰 전에 환자에게 확인할 요약 질문 한 문장('정리하면 ~시죠?', 30자 이내, 환자가 말한 사실만).
JSON 하나만 출력:
{"dx": [{"name": "", "why": ""}], "questions": [{"q": "", "if_yes": [""]}], "exams": [""], "summary": ""}"""

    def make_plan(self) -> dict:
        cands = []
        if self.complaint:
            try:
                cands = self.db.candidates(self.complaint, age=self.age, sex=self.sex, k=6)
            except Exception:  # noqa: BLE001
                cands = []
        proto = PROTO.get(self.complaint or "default") or PROTO.get("default") or {}
        menu_q = [it["text"] for it in proto.get("items", []) if it.get("kind") == "q"][:12]
        exam_ids = [e["id"] for e in proto.get("exams", [])] + COMMON_EXAMS
        if self.complaint:
            exam_ids = list(self.db.items.get(self.complaint, {}).get("exam", [])) + exam_ids
        menu_x = []
        for e in exam_ids:
            if e in self.db.exams and self.db.exams[e]["ko"] not in menu_x:
                menu_x.append(self.db.exams[e]["ko"])
        lines = [f"의사: {x['q']}\n환자: {x['a']}" for x in self.qa]
        user = (f"[환자] {self.age or '?'}세 {('남' if self.sex == 'M' else '여' if self.sex == 'F' else '?')}\n"
                f"[시작 진술] {self.opening}\n[활력징후] {self.vitals}\n[대화]\n" + "\n".join(lines)
                + "\n[온톨로지 후보 진단] " + ", ".join(c["ko"] for c in cands)
                + "\n[이 주호소의 표준 질문 예] " + " / ".join(menu_q)
                + "\n[진찰 메뉴] " + ", ".join(menu_x[:30])
                + f"\n[남은 질문·진찰 턴] {max(0, ASK_CAP - self.turn - 1)}")
        got = parse_json(self.chat(self.PLAN_SYSTEM, user, 4096)) or {}
        self.dx = [d for d in (got.get("dx") or []) if isinstance(d, dict) and d.get("name")][:3]
        if not self.dx and cands:
            self.dx = [{"name": c["ko"], "why": "온톨로지 후보"} for c in cands[:3]]
        self.summary = nfc(got.get("summary", ""))
        qs = []
        for item in got.get("questions") or []:
            if isinstance(item, str):
                item = {"q": item, "if_yes": []}
            if not isinstance(item, dict):
                continue
            q = nfc(item.get("q", ""))
            if self.valid_q(q) and all(bigram_sim(q, x["q"]) < 0.6 for x in qs):
                fu = [nfc(f) for f in (item.get("if_yes") or []) if isinstance(f, str)]
                qs.append({"q": q, "if_yes": [f for f in fu if fits(f) and f.endswith("?") and not COMPOUND.search(f)][:2]})
        # 계획이 비었거나 모자라면 온톨로지(주호소 프로토콜·후보 진단의 핵심 소견)로 채운다
        backup = list(menu_q)
        for c in cands[:3]:
            for fid in c.get("unknown_key", []):
                act = self.db._action(fid, "core", "key")
                if act and act["type"] == "SAY":
                    backup.append(act["text"])
        for q in backup:
            if len(qs) >= 14:
                break
            q = nfc(q)
            if self.valid_q(q) and all(bigram_sim(q, x["q"]) < 0.6 for x in qs):
                qs.append({"q": q, "if_yes": []})
        exams = []
        for name in list(got.get("exams") or []) + [self.db.exams[e]["ko"] for e in exam_ids if e in self.db.exams]:
            eid = self.exam_id(nfc(name))
            if eid and eid not in exams:
                exams.append(eid)
            if len(exams) >= 7:
                break
        return {"questions": qs, "exams": exams}

    def exam_id(self, name: str):
        for eid, e in self.db.exams.items():
            if name in (e["ko"], e["action"]):
                return eid
        hits = [(len(e["ko"]), eid) for eid, e in self.db.exams.items() if len(e["ko"]) >= 3 and e["ko"] in name]
        return max(hits)[1] if hits else None

    # ---- 3·4. 실행 -----------------------------------------------------------------------------------
    BASELINE = [("pmh", "앓고 계신 지병이 있으세요?"), ("meds", "드시고 있는 약이 있으세요?"),
                ("allergy", "약 알레르기가 있나요?"), ("smoke", "담배를 피우시나요?"), ("alcohol", "술을 자주 드시나요?"),
                ("family", "가족 중 앓는 병이 있는 분이 계신가요?")]

    def execute(self, plan):
        queue = [dict(x, tag="plan") for x in plan["questions"]]
        if self.sex == "F" and self.age and 12 <= self.age <= 55:
            self.BASELINE = self.BASELINE + [("preg", "임신 가능성이 있으신가요?")]
        base = [{"q": q, "if_yes": [], "tag": "base:" + k} for k, q in self.BASELINE
                if not (k in ("smoke", "alcohol") and self.age is not None and self.age < 15)]
        exams = list(plan["exams"])
        reserve = len(exams) + (1 if self.summary else 0)
        # 기본 병력은 계획 질문 사이사이가 아니라 계획 질문 뒤, 진찰 앞에 (끊김 없이)
        queue = queue + base
        while queue and self.room() and self.turn < ASK_CAP - reserve and self.left() > TIME_MARGIN:
            item = queue.pop(0)
            q = item["q"]
            if not self.valid_q(q):
                continue
            q_sent = self.with_ack(q)
            a = self.say(q_sent, item["tag"])
            if a is None:
                if self.stopped:
                    return
                continue
            if q_sent != q:                       # 기억할 질문은 호응을 뗀 원문
                self.qa[-1]["q"] = q
                self.asked[-1] = q
            if REFUSE.search(a):
                continue
            if not is_neg(a) and not UNSURE.search(a):
                queue = [{"q": f, "if_yes": [], "tag": "fu"} for f in item.get("if_yes", [])] + queue
            self.pending_ack = self.listen(queue)
        # 중간 요약 → 진찰
        if self.summary and fits(self.summary) and self.summary.endswith("?") and self.room() and self.left() > TIME_MARGIN:
            a = self.say(self.summary, "summary", kind="summary")
        for eid in exams:
            if not self.room() or self.turn >= ASK_CAP or self.left() < TIME_MARGIN:
                break
            self.exam(self.db.exams[eid]["action"])

    pending_ack = ""
    LISTEN_SYSTEM = """외래 문진 중입니다. 방금 환자 답을 듣고 두 가지를 정합니다.
1. ack: 방금 답의 내용을 짧게 되짚는 호응 (12자 이내, 존댓말 '요.'로 끝, 질문 아님, 판단·안심·진단 없음).
   예: '넉 달째 매일이시군요.' '하루 반 갑이시군요.' '걱정 많이 되셨겠어요.' 특별한 내용이 없으면 "".
2. skip: [다음 질문]중 환자가 이미 말한 것으로 답이 나온 번호와, 근거가 된 환자 말 그대로(quote). 확실할 때만.
JSON 하나만: {"ack": "", "skip": [{"n": 1, "quote": ""}]}"""

    def listen(self, queue) -> str:
        """의미 있는 답 뒤에만(모델 1회): 호응 문장과 '이미 들은 질문' 건너뛰기."""
        last = self.qa[-1]["a"] if self.qa else ""
        if len(last) < 8 or is_neg(last) or UNSURE.search(last) or REFUSE.search(last):
            return ""
        nxt = [x["q"] for x in queue[:5]]
        user = ("[시작 진술] " + self.opening + "\n[대화]\n" + "\n".join(f"의사: {x['q']}\n환자: {x['a']}" for x in self.qa[-12:])
                + "\n[앞에서 쓴 호응] " + (" / ".join(self.acks) or "(없음)")
                + "\n[다음 질문]\n" + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(nxt)))
        got = parse_json(self.chat(self.LISTEN_SYSTEM, user, 1024, optional=True)) or {}
        heard = "|".join(re.sub(r"\s", "", h) for h in self.heard())
        drop = set()
        for s in got.get("skip") or []:
            try:
                n = int(s.get("n")) - 1
                quote = re.sub(r"\s", "", nfc(s.get("quote", "")))
            except (TypeError, ValueError, AttributeError):
                continue
            if 0 <= n < len(nxt) and len(quote) >= 4 and quote in heard:
                drop.add(nxt[n])
        if drop:
            queue[:] = [x for x in queue if x["q"] not in drop]
            for q in drop:
                self.asked.append(q)               # 들은 것으로 기록 (기록 단계에서 인용과 함께 남음)
                self.qa.append({"q": q, "a": "(앞 답에서 확인)", "tag": "heard", "kind": "heard"})
        ack = nfc(got.get("ack", ""))
        if (ack and len(ack) <= 14 and ack.endswith("요.") and "?" not in ack
                and not re.search(r"괜찮|정상|진단|가능성|검사", ack)
                and not re.fullmatch(r"(네,?\s*)?(알겠어요|알겠습니다)\.", ack)
                and all(bigram_sim(ack, x) < 0.7 for x in self.acks) and len(self.acks) < 12):
            return ack
        return ""

    def with_ack(self, q: str) -> str:
        ack, self.pending_ack = self.pending_ack, ""
        if ack and fits(ack + " " + q):
            self.acks.append(ack)
            return ack + " " + q
        return q

    # ---- 5. 기록 -------------------------------------------------------------------------------------
    RECORD_SYSTEM = """진료 대화만 근거로 초진 기록을 작성합니다. 확인하지 않은 사실은 쓰지 않습니다.
시작 정보(첫 진술, 활력징후)는 확인된 사실입니다. 대화에서 확인한 것은 '있다'와 '없다' 모두 빠짐없이 씁니다.
(+)/(-)는 대화나 진찰로 확인한 항목에만 씁니다. 진단명은 원인·유형까지 구체적으로 씁니다.
[온톨로지 표준 계획]이 있으면 대화 사실과 맞는 범위에서 P(검사·치료·처치 결정·추적·교육)에 반영하고, '하면 안 되는 처치'는 쓰지 않습니다.
[온톨로지 후보 진단 순위]는 감별진단(A.differential)을 고를 때 참고합니다(대화와 맞지 않으면 쓰지 않음).
JSON 객체 하나만 출력하세요. 모든 값은 한국어 문자열입니다.
{"S": {"cc": "C.C : 주호소 / Onset : 시작 시점 / 양상·부위·기간", "hpi": "P.I : 경과와 대화에서 확인한 사실",
       "pmh": "과거력, 복용 약(이름·양), 알레르기", "fh": "가족력", "sh": "흡연·음주(양)·직업·생활", "ros": "(+)/(-) 목록"},
 "O": {"exam": "활력징후와 부위별 진찰 소견", "tests": ""},
 "A": {"evidence": "#1. 주진단\\n- 근거 : 수집한 사실", "differential": "r/o 진단명 : 이유 (2~4개)"},
 "P": {"tests": "추가 검사와 이유", "treatment": "치료", "disposition": "외래 추적/당일 평가/응급실 등 처치 결정과 근거",
       "follow_up": "재진 시점과 볼 것", "education": "환자 교육"},
 "diagnosis": "가장 가능성 높은 주진단 하나"}"""

    def write_record(self):
        lines = [f"의사: {x['q']}\n환자: {x['a']}" for x in self.qa if x["kind"] != "heard"]
        lines += [f"진찰({n}): {r}" for n, r in self.exams]
        hint = "\n[진료 중 세운 유력 진단] " + ", ".join(d["name"] for d in self.dx) if self.dx else ""
        # R1b: 온톨로지를 SOAP에 다시 연결 — 유력 진단의 표준 계획(검사·치료·처치·교육·금지)과 후보 진단 순위
        kb_ref = ""
        for d in self.dx[:2]:
            ref = self.kb_plan_text(d.get("name", ""))
            if ref:
                kb_ref += f"\n[온톨로지 표준 계획: {ref[0]}]\n{ref[1]}"
        cands = self.kb_candidates()
        if cands:
            kb_ref += "\n[온톨로지 후보 진단 순위] " + ", ".join(cands)
        user = f"[시작 진술] {self.opening}\n[활력징후] {self.vitals}{hint}{kb_ref}\n[대화]\n" + "\n".join(lines)
        got = {}
        for _ in range(2):
            got = parse_json(self.chat(self.RECORD_SYSTEM + "\n(초진 기록)", user, 4096)) or {}
            if str(got.get("diagnosis") or "").strip():
                break
        note = empty_record()
        for sec, fields in RECORD_FIELDS.items():
            vals = got.get(sec) if isinstance(got.get(sec), dict) else {}
            for f in fields:
                v = vals.get(f) or ""
                note[sec][f] = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        dx = " ".join(str(got.get("diagnosis") or "").split()) or (self.dx[0]["name"] if self.dx else "진단 미정")
        # R1b: 모델이 비운 A·P 칸은 온톨로지(최종 주진단의 표준 계획, 후보 진단)로 채운다
        try:
            d = self.db.normalize_diagnosis(dx)
            plan = self.db.plan(d["id"]) if d and d.get("id") else {}
        except Exception:  # noqa: BLE001
            plan = {}
        fill = {"tests": plan.get("test"), "treatment": plan.get("treat"), "follow_up": [e for e in plan.get("edu", []) if re.search(r"재진|추적|주 뒤|주 후|일 뒤|다시", e)],
                "education": plan.get("edu")}
        for f, vals in fill.items():
            if vals and not note["P"][f].strip():
                note["P"][f] = " / ".join(vals[:4])
        if plan.get("dispo") and not note["P"]["disposition"].strip():
            note["P"]["disposition"] = str(plan["dispo"])
        if not note["A"]["differential"].strip():
            others = [c for c in self.kb_candidates() if c != dx][:3] or [x["name"] for x in self.dx[1:3]]
            note["A"]["differential"] = "\n".join(f"r/o {c}" for c in others)
        if not note["A"]["evidence"].strip():
            note["A"]["evidence"] = f"#1. {dx}"
        # 들은 것은 모두 기록 (채점: '했고 기록했는가')
        pos, neg = [], []
        for x in self.qa:
            if x["kind"] in ("open",) or REFUSE.search(x["a"]) or x["tag"] == "concern":
                continue
            (neg if is_neg(x["a"]) else pos).append(f"{x['q'].rstrip('?')} → {x['a']}")
        if pos:
            note["S"]["hpi"] = (note["S"]["hpi"].rstrip() + "\n[문진에서 환자가 말한 내용] " + " / ".join(pos)).strip()
        if neg:
            note["S"]["ros"] = (note["S"]["ros"].rstrip() + "\n[문진에서 없다고 한 것] " + " / ".join(neg)).strip()
        if self.concern:
            note["S"]["hpi"] += "\n환자의 걱정·요청: " + self.concern
        if self.exams:
            note["O"]["exam"] = (note["O"]["exam"].rstrip() + "\n[진찰 결과] " + " / ".join(f"{n} {r}" for n, r in self.exams)).strip()
        if not note["O"]["exam"].startswith(("V/S", "활력")) and self.vitals:
            note["O"]["exam"] = ("V/S " + " ".join(self.vitals.split()) + "\n" + note["O"]["exam"]).strip()
        return note, dx

    def kb_plan_text(self, name: str):
        try:
            d = self.db.normalize_diagnosis(name)
            p = self.db.plan(d["id"]) if d and d.get("id") else {}
        except Exception:  # noqa: BLE001
            return None
        if not p:
            return None
        parts = [f"- {ko}: " + " / ".join(map(str, p[k][:4])) for k, ko in
                 (("test", "검사"), ("treat", "치료"), ("edu", "교육·재진"), ("unsafe", "하면 안 되는 처치")) if p.get(k)]
        if p.get("dispo"):
            parts.append(f"- 처치 결정: {p['dispo']}")
        return d["ko"], "\n".join(parts)

    def kb_candidates(self) -> list[str]:
        if not self.complaint:
            return []
        try:
            return [c["ko"] for c in self.db.candidates(self.complaint, age=self.age, sex=self.sex, k=5)]
        except Exception:  # noqa: BLE001
            return []

    # ---- 6. 마무리 ----------------------------------------------------------------------------------
    CLOSE_SYSTEM = """외래 진료를 마무리하며 환자에게 직접 말할 문장을 씁니다. 환자는 의학 지식이 없는 일반인입니다.
채점은 '대화에서 실제로 말한 설명'만 인정하고, 누구에게나 할 수 있는 말은 점수가 없습니다.
각 문장은 공백 포함 30자 이내, 쉬운 존댓말('~요.'), decision 외에는 질문 아님. 약 이름·용량은 말하지 않습니다.
[기록]과 [이 병에서 꼭 설명할 것]에 없는 새 진단·검사·약은 말하지 않고, '하면 안 되는 처치'나 검사 계획과 어긋나는 약속을 하지 않습니다.
meaning·cause는 [환자에게서 확인한 사실]의 숫자·표현이나 진찰 이상 소견을 근거로, 증상을 되풀이하지 말고 '왜'를 말합니다.
meaning은 병의 뜻과 이 병에서 조심할 결과 하나(예: 혈전이 생겨 뇌졸중 위험, 진통제가 두통을 부르는 악순환)를 함께 말합니다.
concern은 공감 한마디로 시작해 그 병이 아닐(또는 맞을) 근거를 말합니다. '배제할 수 없어요'처럼 불안만 키우는 말은 쓰지 않습니다.
request는 들어줄 수 없으면 이유와 대안을, treatment는 무엇을 어떻게(줄이는 방법·진료과 의뢰 등), safety는 이 병의 응급 증상 2~3개를 말합니다.
문장끼리 같은 검사·계획을 되풀이하지 않습니다.
JSON 하나만 출력 (해당 없으면 빈 문자열):
{"meaning": "진단을 쉬운 말로 (예: '진통제를 자주 드셔서 생긴 두통 같아요.')",
 "cause": "왜 생겼는지, 환자 사실을 근거로 (예: '한 달 이십 일 넘게 진통제를 드셨어요.')",
 "concern": "[환자 걱정]에 직접: 가능성과 근거 (예: '마비가 없고 신경 진찰이 정상이라 가능성은 낮아요.')",
 "concern_plan": "그 걱정을 무엇으로·언제 확인하는지, 또는 어떤 증상이 생기면 추가 검사를 하는지",
 "request": "[환자 요청]에 답: 들어줄 수 있으면 어떻게, 아니면 이유와 대안",
 "test": "어떤 검사를 왜 하는지", "treatment": "무엇을 왜 하는지 (예: '진통제를 줄이고 예방약을 써요.')",
 "safety": "이 병에서 바로 응급실에 와야 하는 구체적 증상", "follow_up": "언제 다시 와서 무엇을 볼지",
 "decision": "선택지 두 가지와 환자 선호를 묻는 질문 한 문장, 물음표로 끝 (응급이면 빈 문자열)",
 "home": "집에서 할 일 한 가지, 구체적으로 (예: '진통제는 한 달 열흘 미만만 드세요.')"}"""
    ORDER = ("meaning", "cause", "concern", "concern_plan", "request", "test", "treatment", "safety", "follow_up",
             "CHECK", "decision", "home")
    MUST = {"test": re.compile(r"검사|심전도|피검사|사진|확인해|찍어|일지|일기|기록"),
            "treatment": re.compile(r"치료|약을|약은|줄이|끊|조절|감량|중단|예방|쉬|수술|의뢰|진료과|산부인과|내과"),
            "safety": SAFETY,
            "follow_up": re.compile(r"뒤에?|다시 와|다시 오|재진|후에")}

    def teach(self, dx: str) -> tuple[str, dict]:
        try:
            d = self.db.normalize_diagnosis(dx)
            p = self.db.plan(d["id"]) if d and d.get("id") else {}
        except Exception:  # noqa: BLE001
            p = {}
        parts = [f"- {ko}: " + " / ".join(p[k][:4]) for k, ko in
                 (("test", "검사"), ("treat", "치료"), ("edu", "생활 교육·재진"), ("unsafe", "하면 안 되는 처치")) if p.get(k)]
        return "\n".join(parts), p

    def facts(self) -> str:
        out = [f"- {x['q']} → {x['a']}" for x in self.qa
               if x["kind"] == "ask" and len(x["a"]) >= 6 and not is_neg(x["a"]) and not REFUSE.search(x["a"])]
        out += [f"- 진찰 {n}: {r}" for n, r in self.exams if not re.match(r"^(정상|특이 소견 없음)", r)]
        return "\n".join(out[-16:])

    def ok(self, s: str, question=False) -> bool:
        s = nfc(s)
        if not fits(s) or DRUG.search(s) or "결과를 보고 알려" in s:
            return False
        return (s.endswith("?") and s.count("?") == 1) if question else (s.endswith(("요.", "요", "다.")) and "?" not in s)

    def kb_safety(self, p: dict) -> str:
        for e in p.get("edu", []):
            m = re.search(r"(.+?)\s*(시|면)?\s*(즉시|바로)\s*(내원|응급실|진료)", e)
            if m:
                w = m.group(1).strip()
                last = w[-1] if w else ""
                josa = "이" if ("가" <= last <= "힣" and (ord(last) - 0xAC00) % 28) else "가"
                s = f"{w}{josa} 생기면 바로 응급실에 오세요."
                if fits(s):
                    return s
        proto = PROTO.get(self.complaint or "default") or {}
        return proto.get("safety") or PROTO.get("default", {}).get("safety") or "갑자기 심해지면 바로 응급실에 오세요."

    def closing(self, note, dx) -> list[str]:
        teach, plan = self.teach(dx)
        request = self.concern if REQUEST_CUE.search(self.concern or "") else ""
        urgent = bool(URGENT.search(note["P"].get("disposition", "")))
        user = (f"[기록]\n주진단: {dx}\n근거: {note['A'].get('evidence', '')[:300]}\n감별: {note['A'].get('differential', '')[:200]}\n"
                f"검사 계획: {note['P'].get('tests', '')[:200]}\n치료: {note['P'].get('treatment', '')[:200]}\n"
                f"처치 결정: {note['P'].get('disposition', '')}\n추적: {note['P'].get('follow_up', '')[:150]}"
                + (f"\n[이 병에서 꼭 설명할 것]\n{teach}" if teach else "")
                + f"\n[환자에게서 확인한 사실]\n{self.facts()}"
                + f"\n[환자 걱정] {self.concern or '(말하지 않음)'}\n[환자 요청] {request or '(말하지 않음)'}")
        got = parse_json(self.chat(self.CLOSE_SYSTEM + "\n(마무리하며)", user, 4096)) or {}
        picked = {}
        for k in self.ORDER:
            if k == "CHECK":
                continue
            s = nfc(got.get(k, ""))
            if k in ("concern", "concern_plan") and not self.concern:
                continue
            if k == "request" and not request:
                continue
            if k == "decision" and urgent:
                continue
            if self.ok(s, question=(k == "decision")) and all(bigram_sim(s, x) < 0.55 for x in picked.values()):
                picked[k] = s
        if "meaning" not in picked:
            picked["meaning"] = f"{dx} 가능성이 높아요." if fits(f"{dx} 가능성이 높아요.") else "검사로 원인을 확인해 볼게요."
        if "safety" not in picked or not SAFETY.search(picked["safety"]):
            picked["safety"] = self.kb_safety(plan)
        if "test" not in picked:
            line = next((x for x in plan.get("explain", []) if self.MUST["test"].search(x) and self.ok(x)), "")
            if line:
                picked["test"] = line
        picked["CHECK"] = CHECK_Q
        out = [picked[k] for k in self.ORDER if k in picked]
        budget = min(CLOSE_CAP, max(4, 50 - self.turn - 1 - REPLY_CAP - 1))
        drop_order = ["home", "decision", "concern_plan", "cause", "request", "follow_up", "treatment", "test"]
        while len(out) > budget and drop_order:
            k = drop_order.pop(0)
            if k in picked and picked[k] in out:
                out.remove(picked[k])
        return self.speak(out, note, dx, teach)

    ANSWER_SYSTEM = """진료 마무리 중 환자가 한 질문·걱정에 바로 답합니다. 쉬운 존댓말 한 문장, 공백 포함 30자 이내, 문장만 출력.
(1) 예/아니요나 가능성을 먼저, (2) 진찰·문진 근거 또는 무엇으로 언제 확인하는지, 들어줄 수 없는 요청이면 이유와 대안.
'결과 보고 알려 드릴게요'처럼 미루지 않고, [이미 한 설명]을 되풀이하지 않습니다.
[이 병에서 꼭 설명할 것]의 검사·'하면 안 되는 처치'와 어긋나는 약속을 하지 않습니다.
같은 걱정을 다시 말하면 공감하고, 걱정한 병과 지금 의심하는 병의 차이처럼 [이미 한 설명]에 없던 새 근거를 말합니다.
[이미 한 설명]의 검사·계획을 그대로 되풀이할 수밖에 없으면 빈 줄만 출력합니다."""

    def answer(self, question, note, dx, teach, said) -> str:
        if self.left() < 240:
            return ""
        user = (f"[주진단] {dx}\n[처치 결정] {note['P'].get('disposition', '')}\n"
                + (f"[이 병에서 꼭 설명할 것]\n{teach}\n" if teach else "")
                + f"[환자에게서 확인한 사실]\n{self.facts()}\n[이미 한 설명] {' / '.join(said[-8:])}\n[환자 질문] {question}")
        for _ in range(2):
            t = nfc(self.chat(self.ANSWER_SYSTEM, user, 2048)).splitlines()
            t = t[0].strip().strip('"') if t else ""
            if self.ok(t) and all(bigram_sim(t, s) < 0.6 for s in said) and not repeats(t, said):
                return t
        return ""

    def speak(self, out, note, dx, teach) -> list[str]:
        said, replies, answered, after_check_done = [], 0, [], False
        for s in out:
            if not self.room(2):
                break
            keep = s == CHECK_Q or SAFETY.search(s) or self.MUST["follow_up"].search(s)
            if (not keep and repeats(s, said)) or (keep and s != CHECK_Q and said and max(bigram_sim(s, x) for x in said) >= 0.6):
                continue                                   # 이미 말한 검사·계획의 되풀이는 말하지 않음
            reply = self.say(s, "close", kind="close")
            if reply is None:
                break
            said.append(s)
            core = ACK_PATIENT.sub("", reply)
            asks = bool(core) and bool(ASK_CUE.search(core)) and not re.search(r"감사합니다\.?$|감사해요\.?$", core)
            if not asks:
                continue
            same = any(bigram_sim(core, q) >= 0.35 for q in answered)
            after_check = s == CHECK_Q and not after_check_done
            if (replies < REPLY_CAP and not same) or after_check:
                ans = self.answer(core, note, dx, teach, said)
                if not ans and after_check and re.search(r"걱정|불안|무서|겁", core):
                    ans = "걱정되시는 마음 알아요, 검사로 꼭 확인할게요."
                    if repeats(ans, said):
                        ans = ""
                if ans and self.room(2):
                    if self.say(ans, "reply", kind="close") is not None:
                        said.append(ans)
                        answered.append(core)
                        replies += 0 if after_check else 1
                        after_check_done = after_check_done or after_check
        if self.room():
            understood = self.say(TEACH_Q, "teach", kind="close")
            if understood and re.search(r"모르겠|잘 모르|헷갈|무슨 말", understood) and self.room():
                again = next((x for x in said if SAFETY.search(x)), "")
                if again and self.say(again, "close", kind="close") is not None:
                    said.append(again)
            if understood:
                note["P"]["education"] = (note["P"]["education"].rstrip() + "\n이해 확인 답변: " + understood).strip()
        return said

    # ---- 제출 ---------------------------------------------------------------------------------------
    def submit(self, note, dx):
        for sec, fields in RECORD_FIELDS.items():
            for f in fields:
                note[sec][f] = str(note[sec].get(f, ""))
        with_retry(self.client.diagnose, note=note, diagnosis=dx or "진단 미정")
        self.submitted = True


def consult(client, db, fallback=None, **_):
    v = Visit(client, db)
    v.submitted = False
    try:
        v.run()
    except Exception:  # noqa: BLE001  — 어떤 오류에서도 기록은 반드시 제출 (제출 없음 = 0점)
        if not v.submitted:
            try:
                note, dx = v.write_record()
            except Exception:  # noqa: BLE001
                note, dx = empty_record(), (v.dx[0]["name"] if v.dx else "진단 미정")
                note["S"]["hpi"] = "\n".join(f"의사: {x['q']} / 환자: {x['a']}" for x in v.qa)
            try:
                v.submit(note, dx)
            except Exception:  # noqa: BLE001
                pass
        else:
            raise
