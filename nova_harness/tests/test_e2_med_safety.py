import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(), "pinned upstream checkout is not installed")
class E2MedicationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_install_replaces_vague_safety_and_restores(self):
        from examples import hybrid_comm
        from nova_agent.e2_med_safety import install, restore

        original_closing = hybrid_comm._closing_sentences
        original_answer = hybrid_comm.ANSWER_SYSTEM
        state = install()
        try:
            self.assertIsNot(hybrid_comm._closing_sentences, original_closing)
            self.assertIn("질문에 먼저 직접 답", hybrid_comm.ANSWER_SYSTEM)
            self.assertLessEqual(len("추가 수면제·술·직접 운전은 피하세요."), 30)
            self.assertLessEqual(len("깨우기 어렵거나 숨이 느리면 119에 연락하세요."), 30)
        finally:
            restore(state)
        self.assertIs(hybrid_comm._closing_sentences, original_closing)
        self.assertEqual(hybrid_comm.ANSWER_SYSTEM, original_answer)


if __name__ == "__main__":
    unittest.main()
