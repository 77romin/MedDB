import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class AblationTests(unittest.TestCase):
    def test_no_knowledge_does_not_load_kb(self):
        from examples.ablation_support import provider
        with patch.dict('os.environ',{'NOVA_KB_MODE':'no_kb'}):
            self.assertIsNone(provider()({'observations':[],'events':[]}))

    def test_runner_rejects_wrong_arm_and_fabricated_metrics(self):
        import sys
        with patch.object(sys,'path',[str(ROOT/'tools'),*sys.path]):
            import run_agent_ablation as runner
        with self.assertRaises(ValueError):runner.validate_output({'case_id':'A','arm':'wrong','diagnosis':'test'},'A','no_kb')
        with self.assertRaises(ValueError):runner.validate_output({'case_id':'A','arm':'no_kb','diagnosis':'test','model_cost':float('nan')},'A','no_kb')
