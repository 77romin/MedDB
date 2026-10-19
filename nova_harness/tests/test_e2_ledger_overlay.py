import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_care.py").exists(), "pinned upstream checkout is not installed")
class E2LedgerOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_install_and_restore_are_reversible(self):
        from examples import hybrid_care
        import meddb.coverage as coverage
        from nova_agent.e2_ledger_overlay import install, restore
        original_consult = hybrid_care.base_consult
        original_coverage = coverage.CareCoverage
        state = install()
        try:
            self.assertIsNot(hybrid_care.base_consult, original_consult)
            self.assertIsNot(coverage.CareCoverage, original_coverage)
        finally:
            restore(state)
        self.assertIs(hybrid_care.base_consult, original_consult)
        self.assertIs(coverage.CareCoverage, original_coverage)


if __name__ == "__main__":
    unittest.main()
