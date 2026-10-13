"""Keep clinical action knowledge and reference ontology evidence separate."""
import json
from pathlib import Path

from .kb import KB


class KnowledgeBridge:
    def __init__(self, clinical, reference=None, mappings=None):
        self.clinical = clinical
        self.reference = reference or KB()
        path = Path(__file__).resolve().parents[1] / 'data/agent/clinical-mappings.json'
        document = mappings if mappings is not None else json.loads(path.read_text(encoding='utf-8'))
        self.mapping_version = document['version']
        self.mappings = document['mappings']
        seen = set()
        for row in self.mappings:
            if row['clinical_id'] not in clinical.findings or row['finding_id'] not in self.reference.nodes:
                raise ValueError('Unknown mapping endpoint')
            if self.reference.nodes[row['finding_id']]['kind'] != 'Finding':
                raise ValueError('Mapping target must be a finding')
            if row['clinical_id'] in seen or row['relation'] != 'exact' or row['review_status'] not in {'draft', 'reviewed'}:
                raise ValueError('Duplicate or unsupported mapping')
            seen.add(row['clinical_id'])

    def support(self, tracker, profile='reviewed'):
        if profile not in {'reviewed', 'pilot', 'research'}:
            raise ValueError('Unknown reference profile')
        enabled = {r['clinical_id']: r for r in self.mappings
                   if r['review_status'] == 'reviewed' or profile == 'research'}
        # Only successful response content can support observations, never attempted actions.
        latest = {}
        for event in tracker.events:
            if event.get('content') and event.get('kind') in {'initial', 'say', 'exam'}:
                latest[event['finding_id']] = event
        observations, events, used, unmapped = [], [], [], []
        ids = set(tracker.present) | set(tracker.absent) | set(tracker.unknown)
        for fid in sorted(ids):
            mapping, event = enabled.get(fid), latest.get(fid)
            if not mapping or not event:
                unmapped.append(fid)
                continue
            eid = f'clinical-{len(events)}'
            events.append({'id': eid, 'kind': event['kind'], 'turn': event['turn'], 'content': event['content'][:2000]})
            state = 'present' if fid in tracker.present else 'absent' if fid in tracker.absent else 'unknown'
            observations.append({'finding_id': mapping['finding_id'], 'state': state, 'evidence_ids': [eid]})
            used.append(mapping)
        result = self.reference.assist(observations, events, profile=profile)
        return {'clinical_version': self.clinical.meta['kb_version'], 'mapping_version': self.mapping_version,
                'mappings_used': used, 'unmapped_or_unconfirmed': unmapped, 'reference': result,
                'confirmation_origin': 'heuristic_or_model_extraction; semantic correctness requires review',
                'interpretation': 'Independent evidence scores; no score fusion or calibrated probability.'}

    def hint(self, tracker, profile='reviewed'):
        result = self.support(tracker, profile)
        ref = result['reference']
        compact = {'version': ref['data_version'], 'profile': profile,
                   'mapping_version': result['mapping_version'], 'mapping_statuses': [r['review_status'] for r in result['mappings_used']],
                   'unmapped_or_unconfirmed': result['unmapped_or_unconfirmed'],
                   'candidates': ref['candidates'][:3], 'next_actions': ref['next_actions'][:4],
                   'warnings': ref['warnings'], 'interpretation': result['interpretation'],
                   'confirmation_origin': result['confirmation_origin']}
        return '[온톨로지 참고 근거: 환자의 관찰 사실과 구분]\n' + json.dumps(compact, ensure_ascii=False)
