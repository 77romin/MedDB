import importlib.util
from pathlib import Path
import json
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'tools/replay_coverage_order.py'
spec=importlib.util.spec_from_file_location('audit_coverage_order',path)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class AuditTests(unittest.TestCase):
    def verify(self,event):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'events.json';p.write_text(json.dumps([event]))
            return audit.verify(p)
    def event(self):
        return {'event':'coverage_order','candidates':[{'target':'urgent','priority':0},{'target':'history','priority':2}],
                'ordered_targets':['urgent','history'],'selected':'urgent'}
    def test_valid_multiset(self):self.assertEqual(self.verify(self.event())['decisions'],1)
    def test_urgent_reordering_rejected(self):
        e=self.event();e.update(ordered_targets=['history','urgent'],selected='history')
        with self.assertRaises(AssertionError):self.verify(e)
    def test_dropped_candidate_rejected(self):
        e=self.event();e['ordered_targets']=['urgent']
        with self.assertRaises(AssertionError):self.verify(e)
    def test_duplicate_target_multiplicity_preserved(self):
        e=self.event();e['candidates'].append({'target':'history','priority':2})
        with self.assertRaises(AssertionError):self.verify(e)

if __name__=='__main__':unittest.main()
