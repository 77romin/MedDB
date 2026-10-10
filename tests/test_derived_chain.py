import json
import tempfile
import unittest
from pathlib import Path
from meddb import KB

class DerivedDiseaseChainTests(unittest.TestCase):
    def test_traversal_continues_through_derived_disease(self):
        kinds = ['Disease', 'Mechanism', 'Disease', 'Mechanism', 'Finding']
        concepts = [dict(id=str(i),kind=k,label_ko=str(i),label_en=str(i),aliases=[],mappings=[]) for i,k in enumerate(kinds)]
        assertions = [dict(id=str(i),subject=str(i),object=str(i+1),predicate=p,
                          source_id='fixture',locator='row',frequency=None,review_status='draft',reviewer=None)
                      for i,p in enumerate(['has_mechanism','causes','has_mechanism','causes'])]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.json'
            path.write_text(json.dumps(dict(format=1,version='fixture',concepts=concepts,assertions=assertions,sources=[dict(id='fixture')])) )
            kb=KB(path)
            result=kb.graph('0',True,4,'out')
            self.assertEqual({n['id'] for n in result['nodes']},set('01234'))
            self.assertEqual(len(kb.graph('0',True,2,'out')['assertions']),2)
            self.assertEqual(kb.graph('0',False,4,'out')['assertions'],[])
