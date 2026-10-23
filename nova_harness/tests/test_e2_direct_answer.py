import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(), "pinned upstream checkout is not installed")
class E2DirectAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_only_answer_prompt_changes_and_restores(self):
        from examples import hybrid_comm
        from nova_agent.e2_direct_answer import DIRECT_ANSWER_SUFFIX, install, restore
        answer = hybrid_comm.ANSWER_SYSTEM
        closing = hybrid_comm.CLOSING_SYSTEM
        closing_function = hybrid_comm._closing_sentences
        original = install()
        try:
            self.assertEqual(hybrid_comm.ANSWER_SYSTEM, answer + DIRECT_ANSWER_SUFFIX)
            self.assertEqual(hybrid_comm.CLOSING_SYSTEM, closing)
            self.assertIs(hybrid_comm._closing_sentences, closing_function)
            self.assertEqual(hybrid_comm.ASK_TURNS, 31)
            self.assertEqual(hybrid_comm.CLOSING_TURNS, 6)
        finally:
            restore(original)
        self.assertEqual(hybrid_comm.ANSWER_SYSTEM, answer)

    def test_instruction_targets_observed_deferral_without_new_facts(self):
        from nova_agent.e2_direct_answer import DIRECT_ANSWER_SUFFIX
        self.assertIn("기록에 답이 있으면", DIRECT_ANSWER_SUFFIX)
        self.assertIn("직접 답하고", DIRECT_ANSWER_SUFFIX)
        self.assertIn("검사 후로 미루지", DIRECT_ANSWER_SUFFIX)


if __name__ == "__main__":
    unittest.main()
