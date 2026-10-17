import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReportTests(unittest.TestCase):
    def test_closing_coverage_counts_successful_say_events_only(self):
        from nova_agent.analysis import analyze
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.jsonl'; trace=Trace(path)
            trace.emit('closing_generated',tag='concern')
            trace.emit('closing_say',tag='safety_net')
            trace.emit('closing_say',tag='safety_net')
            trace.emit('closing_question',response='언제인가요?')
            trace.emit('closing_budget_omission',tag='concern')
            trace.emit('experiment_complete')
            result=analyze(path)
            self.assertEqual(result['closing_sent_by_tag'],{'safety_net':2})
            self.assertEqual(result['closing_omissions_by_tag'],{'concern':1})
            self.assertEqual(result['closing_question_reviews'],1)
            self.assertTrue(any(f['category']=='closing_omission' for f in result['findings']))

    def test_inflight_run_has_no_false_missing_submission_failure(self):
        from nova_agent.analysis import analyze
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'trace.jsonl'; trace = Trace(path)
            trace.emit('experiment_start')
            result = analyze(path)
            self.assertFalse(result['experiment_finished'])
            self.assertFalse(any(f['category'] == 'no_submission_attempt' for f in result['findings']))

    def test_completed_failed_run_is_reported_as_failure(self):
        from nova_agent.analysis import analyze
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'trace.jsonl'; trace = Trace(path)
            trace.emit('experiment_failed')
            result = analyze(path)
            self.assertTrue(result['experiment_finished'])
            self.assertTrue(any(f['category'] == 'no_submission_attempt' for f in result['findings']))

    def test_benchmark_keeps_missing_review_unscored(self):
        from nova_agent.telemetry import Trace
        spec = importlib.util.spec_from_file_location('benchmark_report', ROOT/'tools/benchmark_report.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = {'case_id': 'unpublished-fixture', 'label': 'test', 'agent': 'harness'}
            (root/'manifest.json').write_text(json.dumps(manifest))
            trace = Trace(root/'trace.jsonl'); trace.emit('experiment_failed')
            data, markdown = module.build([root])
            self.assertIsNone(data['runs'][0]['review'])
            self.assertIn('미실행', markdown)
            self.assertNotIn('0/100', markdown)


if __name__ == '__main__': unittest.main()
