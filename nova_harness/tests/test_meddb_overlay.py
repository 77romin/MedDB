import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'vendor/meddb/meddb/api.py').exists(),'pinned upstream checkout is not installed')
class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(ROOT/'vendor/meddb'))
        from meddb import MedDB
        cls.db=MedDB.open()

    def test_medication_questions_only_after_observed_use_and_restore(self):
        import meddb.coverage as coverage
        from examples.hybrid_agent import Tracker
        from nova_agent.meddb_overlay import install,restore
        before=coverage.CareCoverage
        original=install()
        try:
            care=coverage.CareCoverage(self.db,'insomnia',62,'F')
            tracker=Tracker(self.db,'insomnia',62,'F','잠이 안 와요.','')
            targets=lambda:{r['target'] for r in care.needed(tracker)}
            self.assertNotIn('med_strength',targets())
            tracker.mark('hypnotic_use','+',1,'수면제 먹어요')
            self.assertIn('med_strength',targets())
            self.assertIn('med_total_24h',targets())
            care.observe('med_strength','한 알은 몇 mg인가요?','모르겠어요',2)
            self.assertNotIn('med_strength',targets())
            note=self.db.empty_note();care.append_record(note)
            self.assertIn('모르겠어요',note['S']['pmh'])
        finally:restore(original)
        self.assertIs(coverage.CareCoverage,before)


if __name__=='__main__':unittest.main()
