import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/meddb/coverage.py").exists(), "pinned upstream checkout is not installed")
class E2MedicationReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_questions_require_observed_hypnotic_use_and_restore(self):
        import meddb.coverage as coverage
        from examples.hybrid_agent import Tracker
        from meddb import MedDB
        from nova_agent.e2_med_reconciliation import install, restore
        original = coverage.CareCoverage
        state = install()
        try:
            db = MedDB.open()
            care = coverage.CareCoverage(db, "insomnia", 62, "F")
            kb = Tracker(db, "insomnia", 62, "F", "잠을 못 자요", "")
            targets = lambda: {row["target"] for row in care.needed(kb)}
            self.assertNotIn("med_strength", targets())
            kb.mark("hypnotic_use", "+", 1, "수면제를 먹어요")
            expected = {"med_strength", "med_last_taken", "med_total_24h", "med_sources", "other_sedatives"}
            self.assertTrue(expected.issubset(targets()))
        finally:
            restore(state)
        self.assertIs(coverage.CareCoverage, original)


if __name__ == "__main__":
    unittest.main()
