"""Offline fact replay across independent clinical, ontology and integrated views; no model calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from meddb import KB, MedDB
from meddb.bridge import KnowledgeBridge
from examples.hybrid_agent import Tracker


def compare():
    clinical, reference = MedDB.open(), KB()
    bridge = KnowledgeBridge(clinical, reference)
    scenarios = [
        ('uncertain_fever', 'cough', '기침이 있어요. 발열은 모르겠어요.'),
        ('respiratory', 'cough', '기침과 호흡곤란이 있어요.'),
        ('corrected_fever', 'cough', '발열이 있어요.'),
    ]
    runs = []
    for case, complaint, opening in scenarios:
        tracker = Tracker(clinical, complaint, 40, 'M', opening, {})
        if case == 'corrected_fever':
            tracker.note_seen('발열은 없어요.', 1)
        observations = {'present': tracker.present, 'absent': tracker.absent, 'unknown': sorted(tracker.unknown)}
        c = clinical.candidates(complaint, tracker.present, tracker.absent, age=40, sex='M')
        o = bridge.support(tracker, profile='research')
        for mode in ('clinical', 'ontology', 'integrated'):
            runs.append({'case': case, 'mode': mode, 'observations': observations,
                         'clinical_candidates': c if mode != 'ontology' else [],
                         'ontology_support': o if mode != 'clinical' else None})
    return {'kind': 'offline_fact_replay', 'model_calls': 0, 'diagnostic_accuracy_measured': False,
            'clinical_version': clinical.meta['kb_version'], 'reference_version': reference.version,
            'reference_sha256': reference.sha256, 'mapping_version': bridge.mapping_version,
            'runs': runs, 'limitations': ['Synthetic boundary cases, not independent clinical validation.',
                                        'Draft reference mappings enabled for research only.',
                                        'Same observations across views; no score fusion or automated diagnosis.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(ROOT / 'docs/integrated-knowledge-replay.json'))
    args = parser.parse_args()
    result = compare()
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': args.out, 'runs': len(result['runs']), 'model_calls': 0}))
