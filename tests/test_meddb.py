"""python -m unittest discover -s tests"""
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from meddb import MedDB
from meddb.build import SAY_MAX, build_file, load_sources, validate


class KBData(unittest.TestCase):
    def test_validation_is_clean(self):
        errors, warnings = validate(load_sources())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_validator_catches_long_question(self):
        data = load_sources()
        data["slots"][0]["ask"] = "가" * (SAY_MAX + 1) + "?"
        self.assertTrue(any("최대" in e for e in validate(data)[0]))

    def test_validator_catches_bundled_exam(self):
        data = load_sources()
        data["exams"][0]["action"] = "심장 그리고 폐를 청진하겠습니다."
        self.assertTrue(any("하나만" in e for e in validate(data)[0]))

    def test_validator_catches_dangling_reference(self):
        data = load_sources()
        data["diseases"][0]["key"].append("no_such_finding")
        self.assertTrue(any("없는 소견" in e for e in validate(data)[0]))


class Query(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = MedDB.open()

    def test_sqlite_file_matches_memory_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = build_file(Path(tmp) / "meddb.sqlite")
            conn = sqlite3.connect(path)
            try:
                self.assertEqual(conn.execute("SELECT count(*) FROM disease").fetchone()[0], len(self.db.diseases))
            finally:
                conn.close()
            other = MedDB.open(path)
            self.assertEqual(other.kcd_lookup("콜레라"), self.db.kcd_lookup("콜레라"))
        self.assertEqual(other.candidates("chest_pain", ["pressure_chest_pain"]),
                         self.db.candidates("chest_pain", ["pressure_chest_pain"]))

    def test_every_say_text_fits_the_limit(self):
        for cid in self.db.complaints:
            for sex in ("M", "F"):
                for act in self.db.next_actions(cid, age=40, sex=sex):
                    if act["type"] == "SAY":
                        self.assertLessEqual(len(act["text"]), SAY_MAX, act)
                        self.assertEqual(act["text"].count("?"), 1, act)

    def test_complaint_matching_allows_words_in_between(self):
        self.assertEqual(self.db.match_complaint("가슴이 너무 아파서 왔어요.")[0]["id"], "chest_pain")
        self.assertEqual(self.db.match_complaint("어제부터 토하고 설사를 해요")[0]["id"], "vomiting_diarrhea")
        self.assertEqual(self.db.match_complaint("담배 안 피워요"), [])

    def test_vital_flags(self):
        self.assertEqual(self.db.vital_flags({"BP": "150/90", "HR": 102, "RR": 20, "BT": 36.8, "SpO2": 96}),
                         ["tachycardia"])
        self.assertEqual(set(self.db.vital_flags({"SBP": 85, "BT": 38.6, "SpO2": 91, "RR": 24})),
                         {"hypotension", "fever", "hypoxia", "tachypnea"})

    def test_typical_presentations_rank_first(self):
        cases = [
            ("chest_pain", ["pressure_chest_pain", "radiation_arm_jaw", "diaphoresis"], "mi", 58, "M"),
            ("chest_pain", ["tearing_pain_back", "sudden_onset", "bp_arm_difference"], "aortic_dissection", 62, "M"),
            ("abdominal_pain", ["rlq_migration", "anorexia", "rlq_tenderness"], "appendicitis", 24, "M"),
            ("headache", ["thunderclap", "sudden_onset", "neck_stiffness_sx"], "sah", 45, "F"),
            ("dizziness", ["vertigo", "positional_vertigo", "dix_hallpike_positive"], "bppv", 60, "F"),
            ("back_pain", ["bowel_bladder_dysfunction", "saddle_anesthesia"], "cauda_equina", 50, "M"),
            ("fever", ["fever", "flank_pain", "cva_tenderness", "dysuria"], "pyelonephritis", 33, "F"),
            ("urinary", ["dysuria", "frequency_urgency"], "cystitis", 28, "F"),
            ("palpitations", ["abrupt_onset_offset", "palpitations"], "psvt", 30, "F"),
            ("syncope", ["vasovagal_prodrome", "standing_trigger"], "vasovagal_syncope", 20, "F"),
            ("syncope", ["exertional_syncope", "murmur"], "aortic_stenosis", 72, "M"),
            ("rash", ["allergen_exposure", "angioedema", "dyspnea"], "anaphylaxis", 30, "F"),
            ("rash", ["dermatomal_pain", "vesicular_dermatomal"], "herpes_zoster", 65, "M"),
            ("weakness", ["ascending_weakness", "bilateral_weakness", "recent_uri"], "gbs", 40, "M"),
            ("weakness", ["facial_weakness", "facial_droop"], "bell_palsy", 35, "F"),
            ("sore_throat", ["drooling", "muffled_voice", "stridor_sx"], "epiglottitis", 45, "M"),
            ("altered_mental", ["liver_disease", "altered_mental", "asterixis"], "hepatic_encephalopathy", 60, "M"),
            ("cough", ["paroxysmal_cough", "whooping", "posttussive_vomiting"], "pertussis", 30, "F"),
        ]
        for complaint, present, expected, age, sex in cases:
            top = self.db.candidates(complaint, present, age=age, sex=sex)
            self.assertEqual(top[0]["id"], expected, (complaint, [c["id"] for c in top]))

    def test_sex_specific_items_are_filtered(self):
        male = self.db.next_actions("abdominal_pain", age=30, sex="M")
        female = self.db.next_actions("abdominal_pain", age=30, sex="F")
        self.assertNotIn("lmp", [a["target"] for a in male])
        self.assertIn("lmp", [a["target"] for a in female])
        self.assertNotIn("ectopic_pregnancy", [c["id"] for c in self.db.candidates("abdominal_pain", sex="M", k=99)])

    def test_red_flags_clear_once_checked(self):
        pending = self.db.red_flags_pending("chest_pain", age=58, sex="M")
        self.assertIn("aortic_dissection", [p["id"] for p in pending])
        checked = [f for p in pending for f in p["unchecked"]]
        symptoms = [f for f in checked if self.db.findings[f]["kind"] != "sign"]
        exams = {self.db.findings[f]["exam_id"] for f in checked if self.db.findings[f]["kind"] == "sign"}
        self.assertTrue(self.db.red_flags_pending("chest_pain", absent=symptoms, exams_done=exams, age=58, sex="M"))
        self.assertEqual(self.db.red_flags_pending("chest_pain", absent=checked, exams_done=exams, age=58, sex="M"), [])

    def test_ready_only_after_required_steps(self):
        db = self.db
        self.assertFalse(db.ready("cough", age=40, sex="M")["ready"])
        state = {"present": set(), "absent": set(), "asked": set(), "exams_done": set()}
        performed = 0
        for _ in range(60):
            acts = [a for a in db.next_actions("cough", age=40, sex="M", **state) if a["stage"] != "discriminate"]
            if not acts:
                break
            act = acts[0]
            performed += 1
            if act["type"] == "EXAM":
                state["exams_done"].add(act["target"])
                # This fixture simulates an explicitly normal exam, including its findings.
                state['absent'].update(act.get('resolves', []))
            elif act["target"] in db.slots:
                state["asked"].add(act["target"])
            else:
                state["absent"].add(act["target"])
        self.assertTrue(db.ready("cough", age=40, sex="M", **state)["ready"])
        self.assertLessEqual(performed, 25)

    def test_normalize_diagnosis(self):
        self.assertEqual(self.db.normalize_diagnosis("급성 심근경색(STEMI 의심)")["id"], "mi")
        self.assertEqual(self.db.normalize_diagnosis("맹장염")["kcd"], "K35.8")
        self.assertIsNone(self.db.normalize_diagnosis("없는 병"))

    def test_match_findings_handles_negation_per_clause(self):
        got = self.db.match_findings("열은 없고 기침이랑 누런 가래가 나와요. 숨이 차진 않아요.")
        self.assertIn("cough", got["present"])
        self.assertIn("purulent_sputum", got["present"])
        self.assertEqual(got["absent"], ["dyspnea"])

    def test_prevalence_prior_follows_age_and_sex(self):
        self.assertGreater(self.db.prior("mi", 70, "M"), self.db.prior("mi", 25, "F"))
        self.assertGreater(self.db.prior("uri"), self.db.prior("gbs"))
        self.assertIsNone(self.db.prior("ace_cough"))  # KCD 코드가 없는 질환

    def test_kcd_codes_and_lookup(self):
        self.assertEqual(self.db.kcd_lookup("상세불명의 급성 췌장염")["kcd"], "K85.9")
        self.assertEqual(self.db.normalize_diagnosis("콜레라"), {"id": None, "ko": "콜레라", "kcd": "A00"})
        for d in self.db.diseases.values():
            if d["kcd"]:
                self.assertIn(d["kcd"].replace(".", ""), self.db.kcd_names, d["id"])

    def test_external_links_keep_their_source(self):
        sources = self.db.disease("pneumonia")["sources"]
        self.assertEqual(sources["crackles"], "team")          # 진찰 소견은 DDXPlus에 없음
        self.assertEqual(sources["cough"], "team+ddxplus")     # 양쪽 모두
        self.assertIn("ddxplus", set(sources.values()))        # DDXPlus에만 있던 연결
        self.assertEqual(self.db.roles["uri"]["purulent_sputum"], "against")  # 충돌 시 팀 판단 유지

    def test_record_has_official_fields_and_only_confirmed_facts(self):
        from meddb.api import NOTE_FIELDS
        note = self.db.record(
            "chest_pain", present=["pressure_chest_pain", "smoker"], absent=["dyspnea"],
            answers={"onset": "2시간 전"}, turns={"ex_lung_ausc": 7},
            vitals={"BP": "150/90", "HR": 102}, exam_results={"ex_lung_ausc": "양측 깨끗함"})
        self.assertEqual({k: tuple(v) for k, v in note.items()}, NOTE_FIELDS)
        self.assertEqual(note["S"]["cc"], "C.C : 흉통 / Onset : 2시간 전")
        self.assertIn("발생 시점: 2시간 전", note["S"]["hpi"])
        self.assertIn("악화 요인 ( )", note["S"]["hpi"])           # 묻지 않은 슬롯
        self.assertIn("호흡곤란 (-)", note["S"]["ros"])            # 물어서 없다고 확인
        self.assertIn("식은땀 ( )", note["S"]["ros"])              # 필수 문진인데 아직 안 물음
        self.assertNotIn("방사통", note["S"]["ros"])               # 넘겨받지 않은 소견은 적지 않는다
        self.assertIn("흡연 (+)", note["S"]["sh"])
        self.assertIn("폐 청진: 양측 깨끗함 (턴 7)", note["O"]["exam"])
        self.assertEqual(note["O"]["tests"], "")

    def test_assessment_plan_separates_absent_from_unchecked(self):
        ap = self.db.assessment_plan("chest_pain", "mi", present=["pressure_chest_pain"],
                                     absent=["tearing_pain_back"], turns={"pressure_chest_pain": 4}, age=58, sex="M")
        self.assertIn("압박성 흉통 (턴 4)", ap["A"]["evidence"])
        self.assertIn("r/o 대동맥 박리 : 찢어지는 듯한 등 방사통 없음", ap["A"]["differential"])
        self.assertIn("r/o 기흉 : 한쪽 호흡음 감소 미확인", ap["A"]["differential"])
        self.assertTrue(ap["P"]["tests"] and ap["P"]["disposition"])
        self.assertEqual(ap["diagnosis"], "급성 심근경색")

    def test_build_note_passes_the_sdk_check(self):
        # nova_sdk 1.0.0의 RECORD_FIELDS와 Client.diagnose의 검사를 그대로 옮긴 것
        sdk_fields = {"S": ("cc", "hpi", "pmh", "fh", "sh", "ros"), "O": ("exam", "tests"),
                      "A": ("evidence", "differential"),
                      "P": ("tests", "treatment", "disposition", "follow_up", "education")}
        record = self.db.record("chest_pain", present=["pressure_chest_pain"], answers={"onset": "2시간 전"})
        note, diagnosis = self.db.build_note(record, self.db.assessment_plan("chest_pain", "mi", ["pressure_chest_pain"]))
        self.assertTrue(isinstance(note, dict) and set(note) == set(sdk_fields))
        for section, fields in sdk_fields.items():
            self.assertEqual(set(note[section]), set(fields))
            self.assertTrue(all(isinstance(v, str) for v in note[section].values()))
        self.assertEqual(diagnosis, "급성 심근경색")
        self.assertLess(len(json.dumps(note, ensure_ascii=False).encode("utf-8")), 100_000)

    def test_vitals_accept_text_and_loose_keys(self):
        from meddb import parse_vitals
        self.assertEqual(parse_vitals("BP 150/90, HR 102, RR 20, BT 36.8, SpO2 96%")["SBP"], 150.0)
        self.assertEqual(self.db.vital_flags("혈압 85/50 mmHg, 맥박 118회, 체온 38.4"), ["fever", "tachycardia", "hypotension"])
        self.assertEqual(self.db.vital_flags({"bp": "150/90", "hr": 102}), ["tachycardia"])
        self.assertEqual(self.db.vital_flags(None), [])

    def test_guideline_documents(self):
        docs = self.db.guidelines("chest_pain")
        self.assertEqual(docs[0]["title"], "흉통")
        self.assertTrue(all(d["license"] and d["file"] for d in docs))
        self.assertTrue(all(self.db.guidelines(d) for d in self.db.diseases))
        self.assertEqual([d["lang"] for d in self.db.guidelines("mi", lang="ko")], ["ko"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / docs[0]["file"]
            path.parent.mkdir(parents=True)
            path.write_text("---\ntitle: 흉통\n---\n본문", encoding="utf-8")
            found = self.db.guidelines("chest_pain", root=tmp)[0]
            self.assertEqual(found["path"], str(path))
            self.assertEqual(self.db.read_guideline(found["path"], max_chars=7), "---\ntit")
        self.assertIsNone(self.db.read_guideline("/no/such/file.md"))

    def test_plan_and_rubric(self):
        plan = self.db.plan("mi")
        for key in ("test", "treat", "edu", "explain", "unsafe", "dispo"):
            self.assertTrue(plan[key], key)
        rubric = self.db.rubric("chest_pain", "mi")
        self.assertIn("radiation_arm_jaw", rubric["must_ask"])
        self.assertIn("ex_heart_ausc", rubric["must_exam"])
        self.assertNotIn(rubric["main_dx"], rubric["differentials"])


if __name__ == "__main__":
    unittest.main()


class FakeClient:
    """nova_sdk.Client의 응답 모양(session/say/exam/chat/diagnose)만 흉내 낸 가짜. 환자는 정해진 말만 한다."""

    def __init__(self, opening, vitals, yes=()):
        self.opening, self.vitals, self.yes = opening, vitals, yes
        self.log, self.chats, self.submitted, self.turns = [], 0, None, 50

    def session(self):
        return {"initial": {"opening": self.opening, "vital_signs": self.vitals}, "turns_remaining": self.turns}

    def say(self, content):
        assert 0 < len(content) <= 30, content
        self.turns -= 1
        self.log.append(("SAY", content))
        answer = "네, 그래요." if any(k in content for k in self.yes) else "아니요, 없어요."
        return {"content": answer, "turns_remaining": self.turns}

    def exam(self, content):
        assert 0 < len(content) <= 30, content
        self.turns -= 1
        self.log.append(("EXAM", content))
        return {"result": "특이 소견 없음", "turns_remaining": self.turns}

    def chat(self, messages, max_tokens=2048):
        self.chats += 1
        return {"choices": [{"message": {"content": "chest_pain"}}]}

    def diagnose(self, note, diagnosis):
        self.submitted = (note, diagnosis)
        return {"ok": True}


class SkeletonHelpers(unittest.TestCase):
    """공개 샘플(C01·C03·C10)에서 드러난 문제의 회귀 테스트."""

    def test_korean_number_ages(self):
        from examples.consult_skeleton import demographics
        self.assertEqual(demographics("저는 박선희이고, 예순두 살 여자이다."), (62, "F"))
        self.assertEqual(demographics("김도현이고, 여섯 살 남자아이이다. 엄마 김지영, 서른일곱 살이"), (6, "M"))
        self.assertEqual(demographics("육십오 세 남자"), (65, "M"))
        self.assertEqual(demographics("58세 남자"), (58, "M"))
        self.assertEqual(demographics("살이 많이 빠져서 왔다")[0], None)

    def test_sample_openings_route_to_new_complaints(self):
        db = MedDB.open()
        cases = {"잠을 잘 못 자서 병원에 왔다. 수면제를 처방해 달라고 왔다.": "insomnia",
                 "도현이가 또래보다 작다는 말을 듣기 시작했다고 했다.": "short_stature",
                 "최근 석 달 동안 살이 많이 빠져서 병원에 오게 되었다.": "weight_loss"}
        for text, cid in cases.items():
            self.assertEqual(db.match_complaint(text)[0]["id"], cid, text)

    def test_model_complaint_answer_must_be_exact(self):
        from examples.consult_skeleton import pick_complaint

        class Says:
            def __init__(self, text):
                self.text = text

            def chat(self, messages, max_tokens=2048):
                return {"choices": [{"message": {"content": self.text}}]}

        db = MedDB.open()
        opening = "기억이 자꾸 깜빡깜빡해서 왔어요."
        self.assertEqual(pick_complaint(Says("dizziness"), db, opening), "dizziness")
        self.assertIsNone(pick_complaint(Says("none (headache, dizziness 아님)"), db, opening))

    def test_exam_results_are_read_conservatively(self):
        from examples.consult_skeleton import read_exam

        class Asks:
            calls = 0

            def chat(self, messages, max_tokens=2048):
                Asks.calls += 1
                return {"choices": [{"message": {"content": "+"}}]}

        sign = [{"id": "x", "ko": "x"}]
        self.assertEqual(read_exam(Asks(), "비대(-), 결절(-), 압통(-)", sign), {"x": "?"})
        self.assertEqual(Asks.calls, 0)
        # "정상 하한" 같은 말이 있어도 서술형 결과는 모델이 읽는다
        self.assertEqual(read_exam(Asks(), "신장 3백분위수 미만, 성장속도 5cm/년(정상 하한)", sign), {"x": "+"})

    def test_exam_actions_use_standard_exam_names(self):
        db = MedDB.open()
        for eid in ("ex_thyroid_eye", "ex_tremor", "ex_growth_chart", "ex_sedation", "ex_conjunctiva"):
            ex = db.exams[eid]
            self.assertIn(ex["ko"].split()[0], ex["action"], eid)


class KBSelfConsistency(unittest.TestCase):
    def test_agent_reaches_each_disease_from_its_own_findings(self):
        """KB 전체(주호소×질환)를 가상 환자로 돌린다. 공개 샘플과 무관한 회귀 기준."""
        import contextlib
        import io
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import eval_kb
        with contextlib.redirect_stdout(io.StringIO()):
            r = eval_kb.run(seeds=1, keep=0.7, show_misses=False)
        self.assertGreaterEqual(r["top1"], 0.75)
        self.assertGreaterEqual(r["top3"], 0.88)


class ScriptedLLM:
    """하이브리드 시험용 가짜 클라이언트. 의사 LLM의 답을 순서대로 내고, 환자는 정해진 말만 한다."""

    def __init__(self, opening, steps, record, yes=()):
        self.opening, self.steps, self.record, self.yes = opening, list(steps), record, yes
        self.log, self.turn, self.submitted, self.prompts = [], 0, None, []

    def session(self):
        return {"initial": {"opening": self.opening, "vital_signs": "혈압 130/80 mmHg, 맥박 88 회/분, 체온 36.7°C"},
                "turns_remaining": 50 - self.turn}

    def chat(self, messages, max_tokens=2048):
        text = messages[-1]["content"]
        self.prompts.append(text)
        if "주호소를 다음 중" in text:
            out = "none"
        elif "[대화 기록]" in text and "초진 기록" in messages[0]["content"]:
            out = json.dumps(self.record, ensure_ascii=False)
        elif "[남은 턴]" in text:
            out = json.dumps(self.steps.pop(0) if self.steps else {"action": "DONE"}, ensure_ascii=False)
        else:
            out = "?"
        return {"choices": [{"message": {"content": out}}]}

    def say(self, content):
        assert 0 < len(content) <= 30, content
        self.turn += 1
        self.log.append(("SAY", content))
        answer = "네, 그래요." if any(k in content for k in self.yes) else "아니요, 없어요."
        return {"content": answer, "turn": self.turn, "turns_remaining": 50 - self.turn}

    def exam(self, content):
        assert 0 < len(content) <= 30, content
        self.turn += 1
        self.log.append(("EXAM", content))
        return {"result": "압통(-), 반발통(-)", "turn": self.turn, "turns_remaining": 50 - self.turn}

    def diagnose(self, note, diagnosis):
        self.submitted = (note, diagnosis)
        return {"ok": True}


class Hybrid(unittest.TestCase):
    def test_in_kb_uses_hints_picks_and_free_actions(self):
        from examples.hybrid_agent import consult, prepare
        record = {"S": {"cc": "C.C : 흉통"}, "A": {"evidence": "#1. 급성 심근경색"}, "diagnosis": "급성 심근경색"}
        steps = [{"pick": 1}, {"action": "SAY", "content": "가슴을 누르는 느낌인가요?"},
                 {"action": "EXAM", "content": "심음 청진을 하겠습니다."}, {"pick": 99},
                 {"action": "SAY", "content": "심장 검사가 바로 필요해요."}, {"action": "DONE"}]
        client = ScriptedLLM("58세 남자입니다. 가슴이 아파서 왔어요.", steps, record, yes=("누르는",))
        consult(client, prepare())
        note, diagnosis = client.submitted
        self.assertEqual(diagnosis, "급성 심근경색")
        self.assertEqual(note["S"]["cc"], "C.C : 흉통")
        self.assertTrue(note["P"]["tests"])               # LLM이 비운 칸은 KB 초안으로 채운다
        self.assertIn("[추천 행동]", client.prompts[1])
        self.assertIn("심음 청진", client.prompts[1])        # 표준 진찰명 힌트
        self.assertEqual([k for k, _ in client.log], ["SAY", "SAY", "EXAM", "SAY"])

    def test_outside_kb_still_runs_with_generic_hints(self):
        from examples.hybrid_agent import consult, prepare
        record = {"S": {"cc": "C.C : 기억력 저하"}, "diagnosis": "알츠하이머병 치매"}
        steps = [{"action": "SAY", "content": "언제부터 깜빡하셨어요?"}, {"action": "DONE"}]
        client = ScriptedLLM("78세 여자입니다. 기억력이 자꾸 깜빡깜빡해서 왔어요.", steps, record)
        consult(client, prepare())
        note, diagnosis = client.submitted
        self.assertEqual(diagnosis, "알츠하이머병 치매")
        self.assertIn("지식베이스 밖", client.prompts[1])
        self.assertIn("의식·지남력 평가", client.prompts[1])

    def test_falls_back_to_kb_draft_when_llm_record_fails(self):
        from examples.hybrid_agent import consult, prepare
        client = ScriptedLLM("58세 남자입니다. 가슴이 아파서 왔어요.", [{"pick": 1}, {"action": "DONE"}], record={})
        consult(client, prepare())
        note, diagnosis = client.submitted
        self.assertTrue(diagnosis)
        self.assertTrue(note["S"]["cc"])


class Integration(unittest.TestCase):
    def test_skeleton_runs_a_case_end_to_end(self):
        from examples.consult_skeleton import consult, prepare
        from meddb import NOTE_FIELDS
        client = FakeClient("58세 남자 김철수입니다. 가슴이 너무 아파서 왔어요.", "BP 150/90, HR 102, RR 20, BT 36.8, SpO2 96",
                            yes=("누르거나", "팔이나 턱", "식은땀", "담배"))
        consult(client, prepare())
        note, diagnosis = client.submitted
        self.assertEqual(diagnosis, "급성 심근경색")
        self.assertEqual({k: tuple(v) for k, v in note.items()}, NOTE_FIELDS)
        self.assertGreaterEqual(client.chats, 1)                # 예선: 증례마다 모델 호출 1회 이상
        self.assertLessEqual(len(client.log), 26)
        self.assertEqual(len(client.log), len(set(client.log)))  # 같은 말을 두 번 하지 않는다
        self.assertIn("팔·턱 방사통 (+)", note["S"]["ros"])
        self.assertIn("찢어지는 듯한 등 방사통 (-)", note["S"]["ros"])
        self.assertIn("특이 소견 없음 (턴", note["O"]["exam"])
        self.assertIn("r/o 대동맥 박리", note["A"]["differential"])


class Viewer(unittest.TestCase):
    """화면(JS)의 계산이 api.py와 같은 답을 내는지. Node가 없으면 건너뛴다."""

    STATES = [
        ("chest_pain", [], [], [], [], 58, "M"),
        ("chest_pain", ["tachycardia", "pressure_chest_pain", "radiation_arm_jaw"], ["tearing_pain_back", "dyspnea"],
         ["onset", "pmh"], ["ex_lung_ausc"], 58, "M"),
        ("abdominal_pain", ["rlq_migration", "anorexia"], ["diarrhea"], ["onset", "location"], [], 28, "F"),
        ("headache", ["thunderclap", "sudden_onset"], [], [], [], None, None),
        ("syncope", ["vasovagal_prodrome"], ["palpitations", "exertional_syncope"], ["onset"], ["ex_heart_ausc"], 20, "F"),
        ("rash", ["itching"], ["fever"], [], ["ex_rash"], 70, None),
        ("urinary", [], [], [], [], 66, "M"),
    ]

    def test_page_is_self_contained(self):
        from meddb.viewer import render
        html = render(MedDB.open())
        self.assertNotIn("http://", html.split("<script id=\"data\"")[0])   # 외부 스크립트·글꼴 없이 열린다
        self.assertNotIn("<script src", html)
        self.assertIn("급성 심근경색", html)

    @unittest.skipUnless(shutil.which("node"), "node 없음")
    def test_js_matches_python(self):
        from meddb.viewer import CORE_JS, export_data
        db = MedDB.open()
        script = CORE_JS + """
const D = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = D.states.map(([c, p, a, asked, exams, age, sex]) => ({
  cands: candidates(D.data, c, p, a, age, sex, 8).map(r => [r.id, r.score, r.matched, r.against]),
  acts: nextActions(D.data, c, p, a, asked, exams, age, sex).map(x => [x.stage, x.type, x.text, x.target]),
  flags: redFlagsPending(D.data, c, p, a, exams, age, sex).map(r => [r.id, r.unchecked]),
}));
console.log(JSON.stringify(out));
"""
        payload = json.dumps({"data": export_data(db), "states": self.STATES}, ensure_ascii=False)
        result = subprocess.run(["node", "-e", script], input=payload, capture_output=True, text=True, encoding="utf-8", check=True)
        for state, js in zip(self.STATES, json.loads(result.stdout)):
            c, present, absent, asked, exams, age, sex = state
            py_cands = db.candidates(c, present, absent, age, sex, k=8)
            self.assertEqual([r[0] for r in js["cands"]], [r["id"] for r in py_cands], state)
            for (did, score, matched, against), py in zip(js["cands"], py_cands):
                self.assertAlmostEqual(score, py["score"], delta=0.011, msg=did)
                self.assertEqual((matched, against), (py["matched"], py["against"]), did)
            py_acts = db.next_actions(c, present, absent, asked, exams, age, sex)
            self.assertEqual(js["acts"], [[a["stage"], a["type"], a["text"], a["target"]] for a in py_acts], state)
            py_flags = db.red_flags_pending(c, present, absent, exams, age, sex)
            self.assertEqual(js["flags"], [[r["id"], r["unchecked"]] for r in py_flags], state)
