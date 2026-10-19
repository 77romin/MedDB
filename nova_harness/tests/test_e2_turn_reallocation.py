import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(), "pinned upstream checkout is not installed")
class E2TurnReallocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_patch_contains_delivery_guards_and_restores(self):
        from examples import hybrid_care, hybrid_comm
        from nova_agent.e2_turn_reallocation import install, patched_source, restore
        source = Path(hybrid_comm.__file__).read_text(encoding="utf-8")
        patched = patched_source(source)
        self.assertIn("불면 인지행동치료", patched)
        self.assertIn('note["P"]["education"] = (note["P"]["education"].rstrip()', patched)
        self.assertIn("24시간 안에 복용량과 상태", patched)
        original = hybrid_care.base_consult
        state = install()
        try:
            self.assertIsNot(hybrid_care.base_consult, original)
        finally:
            restore(state)
        self.assertIs(hybrid_care.base_consult, original)


if __name__ == "__main__":
    unittest.main()
