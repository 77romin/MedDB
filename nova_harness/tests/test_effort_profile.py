import unittest
from nova_agent.config import Config
from nova_agent.protocol import Gateway
from test_harness import ScriptClient


class EffortProfileTests(unittest.TestCase):
    def capture(self,config):
        class Client(ScriptClient):
            def __init__(self):
                super().__init__([{'ok':True},{'ok':True}]); self.efforts=[]
            def chat(self,*args,**kwargs):
                self.efforts.append(kwargs.get('reasoning_effort'))
                return super().chat(*args,**kwargs)
        client=Client();gateway=Gateway(client,config)
        gateway.chat([]);gateway.chat([],final=True)
        return client.efforts

    def test_low_planning_preserves_medium_final_assessment(self):
        self.assertEqual(self.capture(Config(planner_reasoning_effort='low')),['low','medium'])

    def test_medium_planning_reproduces_previous_compute_profile(self):
        self.assertEqual(self.capture(Config()),['medium','medium'])


if __name__=='__main__':unittest.main()
