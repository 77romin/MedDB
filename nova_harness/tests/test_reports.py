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

    def test_stage_report_missing_run_stays_unscored(self):
        from tools.stage_report import collect_plans, render
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'plan.json'
            path.write_text(json.dumps([{'source':str(Path(d)/'frozen'),
                                        'label':'unrun','case_id':'unpublished-fixture'}]))
            records=collect_plans([path])
            self.assertEqual(records[0]['status'],'not_started')
            self.assertIsNone(records[0]['score'])
            self.assertIsNone(records[0]['official_score'])
            self.assertIn('미검토',render(records))

    def test_scope_and_clinical_semantics_are_not_inferred_from_telemetry(self):
        from nova_agent.analysis import analyze
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.jsonl';t=Trace(p)
            t.emit('decision_goals_updated',accepted=[{'status':'resolved'}],rejected=[])
            t.emit('patient_question_pending',evidence_id='e1')
            t.emit('patient_question_final',evidence_id='e1',answer_evidence_ids=[])
            data=analyze(p)
            self.assertEqual(data['goal_updates_accepted'],1)
            self.assertEqual(data['patient_questions_without_sent_answer'],1)
            self.assertNotIn('clinical_accuracy',data)

    def test_legacy_missing_instrumentation_is_not_reported_as_zero_questions(self):
        from tools.stage_report import collect_plans
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'frozen/results/run';run.mkdir(parents=True)
            manifest={'label':'legacy','case_id':'fixture','agent_version':'0.7.3','fingerprint':{}}
            (run/'manifest.json').write_text(json.dumps(manifest))
            Trace(run/'trace.jsonl').emit('closing_question',response='다음은요?')
            plan=root/'plan.json';plan.write_text(json.dumps([{'source':str(root/'frozen'),'label':'legacy','case_id':'fixture'}]))
            old=collect_plans([plan])[0]
            self.assertIsNone(old['questions_detected'])
            self.assertIsNone(old['goal_updates'])
            manifest.update(agent_version='0.8.3',decision_review=True)
            (run/'manifest.json').write_text(json.dumps(manifest));(run/'trace.jsonl').write_text('')
            new=collect_plans([plan])[0]
            self.assertEqual(new['questions_detected'],0)
            self.assertEqual(new['goal_updates'],0)
            manifest.update(agent_version='future',telemetry_features=['patient_question_tracking'])
            (run/'manifest.json').write_text(json.dumps(manifest))
            future=collect_plans([plan])[0]
            self.assertEqual(future['questions_detected'],0)
            self.assertIsNone(future['goal_updates'])

    def test_interrupted_measurement_is_not_running_or_a_zero_score(self):
        from tools.stage_report import collect_plans
        from nova_agent.telemetry import Trace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run=root/'frozen/results/run';run.mkdir(parents=True)
            (run/'manifest.json').write_text(json.dumps({'label':'interrupted','case_id':'fixture','fingerprint':{}}))
            Trace(run/'trace.jsonl').emit('experiment_start')
            (run/'interruption.json').write_text('{"status":"interrupted"}')
            plan=root/'plan.json';plan.write_text(json.dumps([{'source':str(root/'frozen'),'label':'interrupted','case_id':'fixture'}]))
            row=collect_plans([plan])[0]
            self.assertEqual(row['status'],'interrupted')
            self.assertIsNone(row['score']);self.assertIsNone(row['official_score'])


if __name__ == '__main__': unittest.main()
