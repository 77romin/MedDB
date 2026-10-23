import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(), "pinned upstream checkout is not installed")
class E2PendingQuestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_patch_changes_only_closing_question_control(self):
        from examples import hybrid_comm
        from nova_agent.e2_pending_question import OLD, NEW, patched_source
        source = Path(hybrid_comm.__file__).read_text()
        patched = patched_source(source)
        self.assertEqual(source.count(OLD), 1)
        self.assertIn(NEW, patched)
        self.assertEqual(len(source) - len(OLD), len(patched) - len(NEW))

    def test_install_and_restore_base_consult(self):
        from examples import hybrid_care
        from nova_agent.e2_pending_question import install, restore
        original = hybrid_care.base_consult
        state = install()
        try:
            self.assertIsNot(hybrid_care.base_consult, original)
        finally:
            restore(state)
        self.assertIs(hybrid_care.base_consult, original)


if __name__ == "__main__":
    unittest.main()
