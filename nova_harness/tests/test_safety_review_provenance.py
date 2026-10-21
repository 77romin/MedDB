from copy import deepcopy
import unittest
from tools.review_safety_timeline import validate

class ReviewProvenanceTests(unittest.TestCase):
    def test_review_requires_actual_source_and_successful_speech(self):
        records=[{'note':{'P':{'education':'혼자 끊지 않는다.'}}}]
        speech=[{'index':3,'content':'혼자 끊지 마세요.'}]
        final={'note':{'P':{'education':'혼자 끊지 않는다.'}}}
        check={'plan_ref':{'record_index':0,'field':'education','quote':'혼자 끊지 않는다.'},'spoken_refs':[{'index':3,'quote':'혼자 끊지 마세요.'}],
               'final_ref':{'field':'education','quote':'혼자 끊지 않는다.'},'delivery':'covered','final_consistency':'preserved','reason':'test'}
        payload={'checks':[check],'unspoken_completed_claims':[]}
        self.assertIs(validate(payload,records,speech,final),payload)
        altered=deepcopy(payload);altered['checks'][0]['spoken_refs'][0]['index']=9
        with self.assertRaises(ValueError):validate(altered,records,speech,final)
        altered=deepcopy(payload);altered['checks'][0]['spoken_refs']=[]
        with self.assertRaises(ValueError):validate(altered,records,speech,final)
        altered=deepcopy(payload);altered['checks'][0]['plan_ref']['quote']='새로운 권고'
        with self.assertRaises(ValueError):validate(altered,records,speech,final)
