"""Exercise the real HTTP handler without socket permissions or a browser."""
import io
import json
import unittest
from unittest.mock import patch
from meddb import KB
from meddb.server import serve


class AgentRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        captured={}
        class Server:
            def __init__(self,address,handler):captured['handler']=handler
            def serve_forever(self):pass
        with patch('meddb.server.ThreadingHTTPServer',Server),patch('builtins.print'):
            serve(KB(version='meddb-2026.10.10.3'))
        cls.handler=captured['handler']

    def request(self,path,body=None):
        handler=object.__new__(self.handler)
        handler.path=path;handler.wfile=io.BytesIO();status=[];headers={}
        handler.send_response=lambda code:status.append(code)
        handler.send_header=lambda key,value:headers.update({key:value})
        handler.end_headers=lambda:None
        handler.send_error=lambda code,*args:status.append(code)
        if body is None:handler.do_GET()
        else:
            raw=json.dumps(body).encode();handler.rfile=io.BytesIO(raw);handler.headers={'Content-Length':str(len(raw))};handler.do_POST()
        return status[0],handler.wfile.getvalue(),headers

    def test_normalize_route(self):
        code,body,_=self.request('/api/normalize',{'text':'열이 없어요'})
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['mentions'][0]['proposed_state'],'absent')

    def test_suggest_route_and_reviewed_default(self):
        code,body,_=self.request('/api/suggest',{'observations':{'nova:fever':'present'}})
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['ranking']['candidates'],[])
        code,body,_=self.request('/api/suggest',{'observations':{'nova:fever':'present'},'profile':'pilot'})
        self.assertEqual(code,200)
        self.assertTrue(json.loads(body)['recommendations'])

    def test_invalid_inputs_are_400(self):
        for path,body in [('/api/normalize',{'text':None}),('/api/suggest',{'profile':'bad'}),('/api/suggest',{'observations':{'bad':'present'}})]:
            self.assertEqual(self.request(path,body)[0],400)

    def test_ui_script_route(self):
        code,body,headers=self.request('/agent-ui.js')
        self.assertEqual(code,200)
        self.assertIn(b'renderAgentRecommendations',body)
        self.assertTrue(headers['Content-Type'].startswith('application/javascript'))
