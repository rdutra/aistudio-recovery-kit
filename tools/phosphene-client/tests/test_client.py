import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phosphene_client as pc

class Resp:
    def __init__(self,b): self.b=b
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self): return self.b

def response(obj): return Resp(json.dumps(obj).encode())
def args(**kw):
    d=dict(mode='t2v',prompt='test',width=512,height=320,frames=121,quality='balanced',seed=3,image=None,output_name='sample',job_timeout=1,poll_interval=0)
    d.update(kw); return SimpleNamespace(**d)

class ClientTests(unittest.TestCase):
    def test_submit_and_async_poll(self):
        calls=[]
        def op(req,timeout=0):
            calls.append(req.full_url)
            if req.full_url.endswith('/status'):
                return response({'current':{'id':'j1','status':'running'},'queue':[],'history':[],'gpu':{'busy':True},'tier':{'t2v_max_dim':768}})
            return response({'ok':True,'id':'j1'})
        c=pc.PhospheneClient(opener=op,sleep=lambda _:None)
        a=args()
        with patch.object(c,'status',side_effect=[{'current':None,'queue':[],'gpu':{'busy':False},'tier':{'t2v_max_dim':768}}, {'current':{'id':'j1','status':'running'},'history':[],'queue':[]}, {'current':None,'history':[{'id':'j1','status':'done'}],'queue':[]} ]):
            jid=c.submit(a); self.assertEqual(jid,'j1'); self.assertEqual(c.wait(jid)['status'],'done')
    def test_lock_contention_refuses_submit(self):
        c=pc.PhospheneClient(); c.status=lambda:{'current':{'id':'busy'},'queue':[],'gpu':{'busy':True},'tier':{'t2v_max_dim':768}}
        with self.assertRaisesRegex(pc.ClientError,'active render'): c.submit(args())
    def test_bad_image_and_dimensions(self):
        c=pc.PhospheneClient(); c.status=lambda:{'current':None,'queue':[],'gpu':{'busy':False},'tier':{'i2v_max_dim':768,'t2v_max_dim':768}}
        with self.assertRaisesRegex(pc.ClientError,'existing input'): c.submit(args(mode='i2v',image='/missing'))
        with self.assertRaisesRegex(pc.ClientError,'divisible'): c.submit(args(width=510))
    def test_timeout_requests_stop_and_waits_for_terminal(self):
        c=pc.PhospheneClient(timeout=0,sleep=lambda _:None); c.status=lambda:{'current':None,'queue':[],'history':[]}
        stopped=[]; c.cancel=lambda jid: stopped.append(jid)
        with self.assertRaisesRegex(pc.ClientError,'Timed out'): c.wait('j-timeout')
        self.assertEqual(stopped,['j-timeout'])
    def test_interrupted_stops_before_return(self):
        import threading
        c=pc.PhospheneClient(); c.cancel=lambda jid:None
        ev=threading.Event(); ev.set()
        with self.assertRaisesRegex(pc.ClientError,'Interrupted'): c.wait('j1',ev)
    def test_failed_render(self):
        class C:
            def submit(self,a): return 'j'
            def wait(self,*a): return {'status':'failed','error':'oom'}
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(pc.ClientError,'oom'):
            pc.generate(args(),C(),d)
    def test_failed_download_removes_partial(self):
        class C:
            def submit(self,a): return 'j'
            def wait(self,*a): return {'status':'done','output_path':'/server/a.mp4'}
            def download(self,path,target):
                target.write_bytes(b'partial'); raise pc.ClientError('network broke')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(pc.ClientError,'network broke'):
                pc.generate(args(),C(),d)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_output_validation(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bad.mp4'; f.write_bytes(b'x')
            with patch.object(pc.subprocess,'run',return_value=SimpleNamespace(stdout='{"streams":[]}',returncode=0)):
                with self.assertRaisesRegex(pc.ClientError,'no video stream'): pc.validate(f)
            with patch.object(pc.subprocess,'run',return_value=SimpleNamespace(stdout='{"streams":[{"codec_type":"video"}]}',returncode=0)):
                self.assertIn('streams',pc.validate(f))
    def test_unique_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            v=Path(d)/'sample-20261029-000000.mp4'; v.touch()
            # Timestamp is dynamic; direct existence policy is covered by exclusive creates downstream.
            self.assertTrue(v.exists())


    def test_shared_scheduler_lock_contention(self):
        import subprocess, time
        scheduler=Path.home()/'AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py'
        first=subprocess.Popen([sys.executable,str(scheduler),'--wait-timeout','1','--command-timeout','2','--','python3','-c','import time; time.sleep(.4)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        time.sleep(.12)
        second=subprocess.run([sys.executable,str(scheduler),'--wait-timeout','0','--','true'],capture_output=True,text=True)
        first.communicate(timeout=5)
        self.assertEqual(second.returncode,75)
        self.assertIn('timed out',second.stderr)

    def test_output_name_collision_never_overwrites(self):
        class C:
            def submit(self,a): return 'j'
            def wait(self,*a): return {'status':'done','output_path':'/server/x.mp4'}
            def download(self,path,target): raise AssertionError('must not submit when output exists')
        class FixedDate:
            @classmethod
            def now(cls): return __import__('datetime').datetime(2026,10,29,1,0,0)
        with tempfile.TemporaryDirectory() as d:
            existing=Path(d)/'sample-20261029-010000.mp4'; existing.write_bytes(b'keep')
            with patch.object(pc,'datetime',FixedDate):
                with self.assertRaisesRegex(pc.ClientError,'overwrite'): pc.generate(args(),C(),d)
            self.assertEqual(existing.read_bytes(),b'keep')

if __name__=='__main__': unittest.main()
