"""Audit published aggregates and execute labelled synthetic reader examples.

No SDK, network, patient simulation, clinical judge, or new LLM output is used.
Run from any directory; output paths are resolved against the repository root.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def build():
    from meddb import MedDB
    from examples import hybrid_agent as H, reader_b1_observed as reader

    sources = [
        'nova_harness/reports/b1_rebase_sessions_057.json',
        'nova_harness/reports/b1_rebase_replay_057.json',
        'nova_harness/reports/submission_b1o1_replay_058.json',
        'nova_harness/reports/closing_replay_041.json',
        'nova_harness/reports/plan_delivery_final_052.json',
        'nova_harness/docs/paper/sample_scores.json',
        'examples/reader_b1_observed.py', 'examples/reader_g.py',
        'examples/agent_b1.py', 'examples/hybrid_agent.py',
        'meddb/api.py', 'meddb/data/findings.json',
    ]
    def load(name):
        return json.loads((ROOT / name).read_text(encoding='utf-8'))

    sessions = load(sources[0])['sessions']
    states = Counter()
    modes = {}
    for mode in ('B1', 'B1O1'):
        rows = sorted([s for s in sessions if s['mode'] == mode], key=lambda s: s['case'])
        modes[mode] = [{k: s[k] for k in ('case', 'completed', 'max_server_turn',
                      'elapsed_seconds', 'doctor_attempted_request_ids', 'prompt_tokens', 'errors')}
                      for s in rows]
        if mode == 'B1O1':
            for s in rows:
                states.update(s['observation_states'])
    total = sum(states.values())
    replay = load(sources[1])['sessions']
    zip_replay = load(sources[2])['sessions']
    assert {s['run'] for s in replay} == {s['run'] for s in sessions}
    assert {s['run'] for s in zip_replay} == {s['run'] for s in sessions if s['mode'] == 'B1O1'}
    assert all(s['fingerprint_unchanged'] and s['record_count'] == 1 for s in sessions)
    assert sum(s['linked_observation_rows'] for s in sessions if s['mode'] == 'B1O1') == states['explicit']

    examples = []
    for name, answer, prior in [
        ('bare_yes', '네, 있어요.', False),
        ('partial_denial', '아니요, 자주는 아니에요.', False),
        ('family_scope', '아버지가 손을 떠세요.', False),
        ('other_symptom', '설사는 없어요.', False),
        ('conflict', '아니요, 없어요.', True),
    ]:
        db = MedDB.open()
        reader.install(db)
        kb = H.Tracker(db, 'weight_loss', 40, 'F', '40세 여성입니다.', {}, 'clinical', 'reviewed')
        if prior:
            kb.mark('hand_tremor', '+', 0, '합성 선행 관찰', 'synthetic')
        q = db.findings['hand_tremor']['ask']
        reader.observe(kb, db, q, answer, 1)
        record = db.record(kb.complaint, kb.present, kb.absent, answers=kb.answers,
                           turns=kb.turns, vitals={}, exam_results=kb.exam_results)
        examples.append({'id': name, 'scope': 'synthetic input executed through current reader and deterministic S draft; not a patient session or final LLM SOAP',
                         'prior_hand_tremor_positive': prior,
                         'observation': kb.b1_observations[-1],
                         'tracker': {'present': kb.present, 'absent': kb.absent,
                                     'unknown': sorted(kb.unknown), 'conflicts': sorted(kb.conflicts)},
                         'draft_S': record['S']})
    by_id = {x['id']: x for x in examples}
    assert by_id['bare_yes']['tracker']['present'] == ['hand_tremor']
    assert '손떨림' in by_id['bare_yes']['draft_S']['hpi']
    for name in ('partial_denial', 'family_scope', 'other_symptom'):
        assert 'hand_tremor' not in by_id[name]['tracker']['present'] + by_id[name]['tracker']['absent']
    assert 'hand_tremor' in by_id['conflict']['tracker']['conflicts']

    plan = load(sources[4])['sessions']
    plan_rows = [{'case': s['case'], 'inventoried_groups': s['plan_delivery']['groups'],
                  'sent_success': s['plan_delivery']['states'].get('sent_success', 0),
                  'unresolved': s['plan_delivery']['states'].get('unresolved', 0),
                  'max_server_turn': s['max_server_turn'],
                  'performed_lines_match_acknowledged_speech': s['plan_delivery']['performed_lines_match_acknowledged_speech'],
                  'coverage_verified': s['plan_delivery']['coverage_verified']}
                 for s in sorted(plan, key=lambda s: s['case'])]
    scores = load(sources[5])
    return {
        'scope': '2026-11-08 retrospective audit of published aggregates plus five synthetic code demonstrations; no raw session logs available in this checkout',
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        'b1_comparison': modes,
        'b1o1_observations': {'unit': 'reader observation row, not atomic fact or all session speech',
            'total': total, 'states': dict(sorted(states.items())),
            'single_question_link': states.get('single_question_link', 0),
            'explicit_row_fraction': round(states['explicit'] / total, 6),
            'interpretation_additional_model_calls': [s['interpretation_additional_model_calls'] for s in sessions if s['mode'] == 'B1O1']},
        'historical_replay_evidence': {
            'scope': 'read published historical replay results; raw replay was not rerun',
            'sessions': len(replay),
            'all_match': all(s['all_model_inputs_actions_and_final_note_match'] for s in replay),
            'extracted_zip_sessions': len(zip_replay),
            'all_extracted_zip_match': all(s['extracted_zip_model_inputs_actions_and_final_note_match'] for s in zip_replay)},
        'synthetic_processing_examples': examples,
        'historical_saved_response_closing': load(sources[3]),
        'historical_unadopted_plan_delivery': plan_rows,
        'sample_score_selection': [r for r in scores['rows'] if r['id'] in ('E2', 'E2-Ledger', 'R3a', 'Q1', 'B1O1')],
        'unmeasured': {
            'reader_semantic_accuracy': None, 'appropriateness_of_abstention': None,
            'major_fact_soap_recall': None, 'soap_statement_evidence_precision': None,
            'semantic_question_repetition': None, 'clinical_safety': None,
            'b1o1_reader_causal_score_effect': None},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='nova_harness/docs/paper/retrospective_audit.json')
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    data = build()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'observations': data['b1o1_observations']['total'],
                      'synthetic_examples': len(data['synthetic_processing_examples']), 'network_calls': 0}))


if __name__ == '__main__':
    main()
