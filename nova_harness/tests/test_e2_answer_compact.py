import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / "vendor/meddb/examples/hybrid_comm.py").exists(), "pinned upstream checkout is not installed")
class E2AnswerCompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vendor = str(ROOT / "vendor/meddb")
        sys.path.insert(0, cls.vendor)

    @classmethod
    def tearDownClass(cls):
        if cls.vendor in sys.path:
            sys.path.remove(cls.vendor)

    def test_patch_keeps_complete_last_clause(self):
        from examples import hybrid_comm
        from nova_agent.e2_answer_compact import patched_source
        source = Path(hybrid_comm.__file__).read_text()
        module = type(sys)("test_compact_module")
        module.__file__ = hybrid_comm.__file__
        exec(compile(patched_source(source), module.__file__, "exec"), module.__dict__)
        class H:
            @staticmethod
            def chat(*args):
                return "네, 상태를 평가한 뒤 불면 인지행동치료와 수면위생을 안내해 드릴게요."
        original = module.H.chat
        module.H.chat = H.chat
        try:
            result = module._answer_question(None, {"P": {}}, "진단", "다른 방법이 있나요?")
        finally:
            module.H.chat = original
        self.assertEqual(result, "불면 인지행동치료와 수면위생을 안내해 드릴게요.")
        self.assertLessEqual(len(result), 30)

    def test_patch_recovers_conjunction_suffix_seen_in_api_log(self):
        from examples import hybrid_comm
        from nova_agent.e2_answer_compact import patched_source
        source = Path(hybrid_comm.__file__).read_text()
        module = type(sys)("test_compact_conjunction_module")
        module.__file__ = hybrid_comm.__file__
        exec(compile(patched_source(source), module.__file__, "exec"), module.__dict__)
        original = module.H.chat
        module.H.chat = lambda *args: "불면 인지행동치료와 수면 습관 개선을 함께 해보실 수 있어요."
        try:
            result = module._answer_question(None, {"P": {}}, "진단", "약 말고 방법이 있나요?")
        finally:
            module.H.chat = original
        self.assertEqual(result, "수면 습관 개선을 함께 해보실 수 있어요.")
        self.assertLessEqual(len(result), 30)


if __name__ == "__main__":
    unittest.main()
