import json,threading,unittest
from functools import partial
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from server import LocalServer,Handler,SOLVER
from test_core import fixture

class QuietHandler(Handler):
    def log_message(self,*args):pass

class HttpStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=LocalServer(('127.0.0.1',0),partial(QuietHandler,directory='web'))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(5)

    def post(self,path,body,raw=False):
        req=Request(self.base+path,data=body if raw else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=10) as r:return r.status,json.load(r)
        except HTTPError as e:
            with e:return e.code,json.load(e)

    def test_nonobject_and_malformed_requests_are_client_errors(self):
        for body in [[],None,'bad',123]:
            status,data=self.post('/api/wrap',body)
            self.assertEqual(status,400,data)
        self.assertEqual(self.post('/api/wrap',b'{',True)[0],400)

    def test_failed_and_busy_solves_do_not_poison_next_request(self):
        a,b,p,_=fixture();body={'source':a,'target':b,'pairs':p,'iterations':5}
        self.assertEqual(self.post('/api/wrap',{**body,'pairs':[]})[0],400)
        self.assertTrue(SOLVER.acquire(False))
        try:self.assertEqual(self.post('/api/wrap',body)[0],409)
        finally:SOLVER.release()
        status,data=self.post('/api/wrap',body)
        self.assertEqual(status,200,data);self.assertLess(data['stats']['landmarkMaxError'],1e-8)
        self.assertTrue(SOLVER.acquire(False));SOLVER.release()

if __name__=='__main__':unittest.main()
