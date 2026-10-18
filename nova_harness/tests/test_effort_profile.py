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

    def test_truncated_planner_retry_is_bounded_and_resets_next_turn(self):
        import json
        from nova_agent.runtime import consult, prepare
        class Client(ScriptClient):
            def __init__(self):
                super().__init__([{'next_action':{'type':'SAY','content':'언제부터요?'}},
                                  {'next_action':{'type':'SAY','content':'추가 평가 후 결정하겠습니다.','communication':['plan']}},
                                  {'next_action':{'type':'DONE'}}, {'diagnosis':'평가 중'}],['어제요','네'])
                self.limits=[]
            def chat(self,*args,**kw):
                self.limits.append(kw['max_tokens'])
                if len(self.limits)==1:
                    return {'choices':[{'finish_reason':'length','message':{'content':'{"goal_updates":['}}],
                            'usage':{'prompt_tokens':10,'completion_tokens':2048}}
                return super().chat(*args,**kw)
        c=Client()
        consult(c,prepare(),Config(meddb=False,decision_review=False,structured_closing=False))
        self.assertEqual(c.limits,[2048,3072,2048,2048,4096])
        self.assertEqual(c.turns,48)

    def test_retry_still_respects_reserved_output_budget(self):
        from nova_sdk import NovaError
        g=Gateway(ScriptClient(),Config(output_budget=15000,reserve_output=12000))
        with self.assertRaises(NovaError) as caught:
            g.chat([],max_tokens=3072)
        self.assertEqual(caught.exception.code,'LOCAL_MODEL_BUDGET')


if __name__=='__main__':unittest.main()
