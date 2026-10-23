"""Verify candidate preservation and urgent precedence in recorded decisions.

This is a structural log audit, not regenerated counterfactual observations or a
clinical correctness assessment. Raw patient replies are neither read nor emitted.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def verify(path):
    decisions=[e for e in json.loads(path.read_text()) if e['event']=='coverage_order']
    for e in decisions:
        candidates=e['candidates'];targets=e['ordered_targets']
        if Counter(a['target'] for a in candidates)!=Counter(targets):
            raise AssertionError('candidate multiset changed')
        if not targets or targets[0]!=e['selected']:
            raise AssertionError('logged selected target differs')
        urgent={a['target'] for a in candidates if a.get('priority',99)<=0}
        if urgent and targets[0] not in urgent:
            raise AssertionError('urgent precedence changed')
    return {'run':path.parent.name,'decisions':len(decisions),'failures':0,
            'candidate_multiset_and_urgent_precedence':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('events',nargs='+',type=Path);a=p.parse_args()
    print(json.dumps([verify(path) for path in a.events]))
