import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(
    (ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(),
    "pinned upstream checkout is not installed",
)
class E2CalibratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_overlay_only_changes_and_restores_existing_prompts(self):
        from examples import hybrid_comm
        from nova_agent.e2_calibrated import install, restore, CALIBRATED_CLOSING_SYSTEM
        original_closing = hybrid_comm.CLOSING_SYSTEM
        original_answer = hybrid_comm.ANSWER_SYSTEM
        original_function = hybrid_comm._closing_sentences
        state = install()
        try:
            self.assertEqual(hybrid_comm.CLOSING_SYSTEM, CALIBRATED_CLOSING_SYSTEM)
            self.assertIs(hybrid_comm._closing_sentences, original_function)
            self.assertEqual(hybrid_comm.ASK_TURNS, 31)
            self.assertEqual(hybrid_comm.CLOSING_TURNS, 6)
        finally:
            restore(state)
        self.assertEqual(hybrid_comm.CLOSING_SYSTEM, original_closing)
        self.assertEqual(hybrid_comm.ANSWER_SYSTEM, original_answer)

    def test_closing_contract_has_all_scored_communication_purposes(self):
        from nova_agent.e2_calibrated import CALIBRATED_CLOSING_SYSTEM
        for key in ('diagnosis', 'plan', 'follow_up', 'safety', 'concern'):
            self.assertIn(key, CALIBRATED_CLOSING_SYSTEM)
        self.assertIn('30자', CALIBRATED_CLOSING_SYSTEM)
        self.assertIn('새 진단·검사·약', CALIBRATED_CLOSING_SYSTEM)


if __name__ == '__main__':
    unittest.main()
