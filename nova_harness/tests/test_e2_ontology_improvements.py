import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/meddb/coverage.py").exists(), "pinned upstream checkout is not installed")
class E2OntologyImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_compaction_does_not_append_raw_answers_and_restores(self):
        import meddb.coverage as coverage
        from nova_agent.e2_concept_compaction import install, restore
        original = coverage.CareCoverage
        state = install()
        try:
            obj = object.__new__(coverage.CareCoverage)
            obj.records = {"nutrition": {"question": "밥은?", "answer": "입맛이 없어요", "turn": 3}}
            note = {"S": {"hpi": "식욕저하(+), 최근", "pmh": "", "fh": "", "sh": "", "ros": ""}}
            obj.append_record(note)
            self.assertEqual(note["S"]["hpi"], "식욕저하(+), 최근")
            self.assertNotIn("밥은?", note["S"]["hpi"])
        finally:
            restore(state)
        self.assertIs(coverage.CareCoverage, original)

    def test_value_policy_prioritizes_red_flag_and_top_key(self):
        import meddb.coverage as coverage
        from nova_agent.e2_value_questions import install, restore
        original = coverage.CareCoverage

        class FakeBase:
            def needed(self, kb):
                return [
                    {"type": "SAY", "target": "smoker", "text": "흡연?", "why": "과거력·사회력", "priority": 5},
                    {"type": "SAY", "target": "bloody_stool", "text": "혈변?", "why": "위험 원인 확인: 중증 설사", "priority": 0},
                    {"type": "SAY", "target": "diarrhea", "text": "설사?", "why": "주호소 핵심 소견", "priority": 2},
                ]

        coverage.CareCoverage = FakeBase
        state = install()
        try:
            obj = object.__new__(coverage.CareCoverage)
            kb = type("KB", (), {"conflicts": set(), "ranked": lambda self, k=4: [{"unknown_key": ["diarrhea"]}]})()
            actions = obj.needed(kb)
            self.assertEqual([a["target"] for a in actions], ["bloody_stool", "diarrhea", "smoker"])
            self.assertGreater(actions[0]["decision_value"], actions[-1]["decision_value"])
        finally:
            restore(state)
            coverage.CareCoverage = original

    def test_value_policy_adds_observed_sedative_safety_questions(self):
        import meddb.coverage as coverage
        from nova_agent.e2_value_questions import install, restore
        original = coverage.CareCoverage
        state = install()
        try:
            obj = object.__new__(coverage.CareCoverage)
            obj.complaint = "insomnia"
            obj.records = {}
            obj.attempts = {}
            obj.extra = {}
            kb = type("KB", (), {
                "present": ["hypnotic_use"], "conflicts": set(),
                "ranked": lambda self, k=4: [],
            })()
            # Avoid depending on a full MedDB fixture for the upstream list.
            parent = coverage.CareCoverage.__mro__[1]
            old_needed = parent.needed
            parent.needed = lambda self, kb: []
            try:
                actions = obj.needed(kb)
            finally:
                parent.needed = old_needed
            self.assertEqual(
                {a["target"] for a in actions},
                {"med_strength", "med_last_taken", "med_total_24h", "med_sources", "other_sedatives"},
            )
            self.assertTrue(all(a["decision_value"] == 95 for a in actions))
        finally:
            restore(state)
        self.assertIs(coverage.CareCoverage, original)


if __name__ == "__main__":
    unittest.main()
