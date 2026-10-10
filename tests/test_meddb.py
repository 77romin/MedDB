"""python -m unittest discover -s tests"""
import sqlite3
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
            self.assertEqual(sqlite3.connect(path).execute("SELECT count(*) FROM disease").fetchone()[0],
                             len(self.db.diseases))
            other = MedDB.open(path)
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
        self.assertEqual(self.db.red_flags_pending("chest_pain", absent=symptoms, exams_done=exams, age=58, sex="M"), [])

    def test_ready_only_after_required_steps(self):
        db = self.db
        self.assertFalse(db.ready("cough", age=40, sex="M")["ready"])
        state = {"present": set(), "absent": set(), "asked": set(), "exams_done": set()}
        for _ in range(60):
            acts = [a for a in db.next_actions("cough", age=40, sex="M", **state) if a["stage"] != "discriminate"]
            if not acts:
                break
            act = acts[0]
            if act["type"] == "EXAM":
                state["exams_done"].add(act["target"])
            elif act["target"] in db.slots:
                state["asked"].add(act["target"])
            else:
                state["absent"].add(act["target"])
        self.assertTrue(db.ready("cough", age=40, sex="M", **state)["ready"])
        turns = len(state["asked"]) + len(state["absent"]) + len(state["exams_done"])
        self.assertLessEqual(turns, 25)

    def test_normalize_diagnosis(self):
        self.assertEqual(self.db.normalize_diagnosis("급성 심근경색(STEMI 의심)")["id"], "mi")
        self.assertEqual(self.db.normalize_diagnosis("맹장염")["kcd"], "K35.8")
        self.assertIsNone(self.db.normalize_diagnosis("없는 병"))

    def test_match_findings_handles_negation_per_clause(self):
        got = self.db.match_findings("열은 없고 기침이랑 누런 가래가 나와요. 숨이 차진 않아요.")
        self.assertIn("cough", got["present"])
        self.assertIn("purulent_sputum", got["present"])
        self.assertEqual(got["absent"], ["dyspnea"])

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
