from copy import deepcopy
from types import SimpleNamespace
import unittest
from nova_agent.safety_trace import SafetyTimeline,TimelineClient,digest

class SafetyTraceTests(unittest.TestCase):
    def test_preserves_success_and_never_counts_failed_speech(self):
        sent=[]
        def say(content):
            if content=='failed':raise RuntimeError('rejected')
            sent.append(content);return {'content':'patient reply','turn':2}
        raw=SimpleNamespace(say=say,diagnose=lambda **kw:deepcopy(kw))
        t=SafetyTimeline();c=TimelineClient(raw,t)
        note={'P':{'education':'planned'}};t.record('opening',{},[],note,'dx');note['P']['education']='changed'
        c.say('actual')
        with self.assertRaises(RuntimeError):c.say('failed')
        final={'P':{'education':'final'}};result=c.diagnose(note=final,diagnosis='dx')
        final['P']['education']='changed'
        self.assertEqual(t.records[0]['note']['P']['education'],'planned')
        self.assertEqual(len(t.speech),1);self.assertEqual(len(t.failures),1)
        self.assertEqual(t.final['note']['P']['education'],'final')
        self.assertEqual(result['note']['P']['education'],'final')
    def test_observation_fingerprint_retains_polarity(self):
        self.assertNotEqual(digest({'answer':'없음'}),digest({'answer':'있음'}))

class RetryIdentityTests(unittest.TestCase):
    def test_wrapper_exposes_and_forwards_stable_request_id(self):
        import inspect
        seen=[]
        def say(content,*,request_id=None):seen.append(request_id);return {'content':'reply','turn':1}
        client=TimelineClient(SimpleNamespace(say=say),SafetyTimeline())
        self.assertIn('request_id',inspect.signature(client.say).parameters)
        client.say('hello',request_id='stable')
        client.say('hello',request_id='stable')
        self.assertEqual(seen,['stable','stable'])
