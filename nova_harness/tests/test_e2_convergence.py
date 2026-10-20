import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FakeDB:
    roles = {
        "dx1": {"a": "key", "b": "support", "danger": "against"},
        "dx2": {"a": "against", "b": "key", "danger": "key"},
    }

    def red_flags_pending(self, complaint, present, absent, exams_done, age, sex):
        if "danger" in present or "danger" in absent:
            return []
        return [{"id": "dx2", "ko": "위험질환", "unchecked": ["danger"]}]


class FakeKB:
    complaint = "complaint"
    present = ["a"]
    absent = []
    exams_done = set()
    conflicts = set()
    age = 30
    sex = "F"

    def ranked(self, k=5):
        return [
            {"id": "dx1", "ko": "질환1", "score": 8, "share": .7,
             "matched": ["a"], "against": [], "unknown_key": []},
            {"id": "dx2", "ko": "질환2", "score": 3, "share": .2,
             "matched": [], "against": ["a"], "unknown_key": ["b", "danger"], "red_flag": True},
        ]


class E2ConvergenceTests(unittest.TestCase):
    def test_shadow_tracks_without_calling_scores_probabilities(self):
        from nova_agent.e2_convergence import ConvergenceEngine
        engine = ConvergenceEngine(FakeDB(), "complaint")
        snap = engine.observe(FakeKB(), [{"type": "SAY", "target": "b", "stage": "discriminate"}],
                              {"meds": {}, "allergy": {}, "pregnancy": {}, "breastfeeding": {}})
        self.assertFalse(snap["margin_is_probability"])
        self.assertEqual(snap["candidates"][0]["matched_key"], ["a"])
        self.assertEqual(snap["recommended_existing_action"]["target"], "b")
        self.assertFalse(snap["converged"])
        self.assertTrue(snap["pending_red_flags"])

    def test_repeat_has_high_cost_unless_conflicted(self):
        from nova_agent.e2_convergence import action_utility
        action = {"target": "a", "stage": "discriminate"}
        candidates = FakeKB().ranked()
        repeated = action_utility(FakeDB(), candidates, action, {"a"}, set())
        conflicted = action_utility(FakeDB(), candidates, action, {"a"}, {"a"})
        self.assertLess(repeated["total"], 0)
        self.assertGreater(conflicted["total"], repeated["total"])

    def test_snapshots_are_deterministic(self):
        from nova_agent.e2_convergence import ConvergenceEngine
        actions = [{"type": "SAY", "target": "b", "stage": "discriminate"}]
        records = {"meds": {}, "allergy": {}, "pregnancy": {}, "breastfeeding": {}}
        left = ConvergenceEngine(FakeDB(), "complaint").observe(FakeKB(), actions, records)
        right = ConvergenceEngine(FakeDB(), "complaint").observe(FakeKB(), actions, records)
        self.assertEqual(left, right)

    def test_convergence_requires_two_ready_snapshots(self):
        from nova_agent.e2_convergence import ConvergenceEngine
        kb = FakeKB()
        kb.present = ["a", "danger"]
        kb.absent = []
        kb.ranked = lambda k=5: [
            {"id": "dx1", "ko": "질환1", "score": 8, "share": .8,
             "matched": ["a"], "against": [], "unknown_key": []},
            {"id": "dx2", "ko": "질환2", "score": 3, "share": .1,
             "matched": ["danger"], "against": ["a"], "unknown_key": []},
        ]
        engine = ConvergenceEngine(FakeDB(), "complaint")
        records = {"meds": {}, "allergy": {}, "pregnancy": {}, "breastfeeding": {}}
        first = engine.observe(kb, [], records)
        second = engine.observe(kb, [], records)
        self.assertFalse(first["converged"])
        self.assertTrue(second["converged"])


@unittest.skipUnless((ROOT / "vendor/meddb/meddb/coverage.py").exists(), "pinned upstream checkout missing")
class E2ConvergenceOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_shadow_returns_upstream_actions_unchanged(self):
        import meddb.coverage as coverage
        from nova_agent.e2_convergence_shadow import install, restore
        original = coverage.CareCoverage

        class FakeBase:
            def needed(self, kb):
                return [{"type": "SAY", "target": "b", "stage": "discriminate", "text": "질문"}]

            def trace(self):
                return {"base": True}

        coverage.CareCoverage = FakeBase
        state = install()
        try:
            obj = object.__new__(coverage.CareCoverage)
            obj.records = {"meds": {}, "allergy": {}, "pregnancy": {}, "breastfeeding": {}}
            obj._convergence = __import__("nova_agent.e2_convergence", fromlist=["ConvergenceEngine"]).ConvergenceEngine(FakeDB(), "complaint")
            actions = obj.needed(FakeKB())
            self.assertEqual(actions, [{"type": "SAY", "target": "b", "stage": "discriminate", "text": "질문"}])
            self.assertIn("convergence", obj.trace())
        finally:
            restore(state)
            coverage.CareCoverage = original


if __name__ == "__main__":
    unittest.main()
