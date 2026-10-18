import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
judge=importlib.import_module('judge')


class ReviewReplicaTests(unittest.TestCase):
    def test_replica_preserves_primary_and_reuses_its_own_cached_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';run.mkdir()
            (run/'trace.jsonl').write_text(json.dumps({'event':'experiment_complete'})+'\n')
            (run/'manifest.json').write_text(json.dumps({'case_id':'4fa07144-04e5-4116-a18e-88d8a90cc21a'}))
            (run/'local_review.json').write_text('{"original":true}')
            reference=root/'vendor/samples/nova-samples-2026/C01';reference.mkdir(parents=True)
            for name in ['case.json','model_record.json']:(reference/name).write_text('{}')
            review={'scope':'local_rubric_estimate_not_official',
                    'scores':{key:{'score':0,'reason':'test'} for key in judge.RUBRIC}}
            response={'choices':[{'message':{'content':json.dumps(review)}}],'usage':{}}
            args=['judge.py',str(run),'--public-case','C01','--review-tag','replica']
            with patch.object(judge,'ROOT',root),patch.object(judge,'load_local_env'),\
                 patch.dict('os.environ',{'NOVA_DEV_KEY':'unit-test-placeholder'},clear=True),\
                 patch.object(judge,'LoggedClient'),patch.object(judge,'Gateway') as gateway,\
                 patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):
                gateway.return_value.chat.return_value=response
                judge.main();judge.main()
                self.assertEqual(gateway.return_value.chat.call_count,1)
            self.assertEqual((run/'local_review.json').read_text(),'{"original":true}')
            self.assertEqual(json.loads((run/'local_review_replica.json').read_text())['estimated_total'],0)


if __name__=='__main__':unittest.main()
