import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from replay_observation_session import Replay
from nova_sdk import NovaError

class ReplayErrorTests(unittest.TestCase):
    def test_saved_model_error_is_raised_after_request_validation(self):
        messages=[{'role':'user','content':'test'}]
        c=Replay({},[{'kind':'chat','messages':messages,'max_tokens':20,'response':None,
                      'error':{'code':'MODEL_TOKEN_BUDGET','status':429}}])
        with self.assertRaises(NovaError) as caught:c.chat(messages,20)
        self.assertEqual(caught.exception.code,'MODEL_TOKEN_BUDGET');self.assertEqual(c.remaining,0)
    def test_input_drift_is_not_hidden_by_saved_error(self):
        c=Replay({},[{'kind':'chat','messages':[],'max_tokens':20,'response':None,
                      'error':{'code':'MODEL_TOKEN_BUDGET'}}])
        with self.assertRaises(AssertionError):c.chat([{'role':'user','content':'different'}],20)
