#!/usr/bin/env python3
"""Safe local client for Phosphene's asynchronous LTX video API."""
from __future__ import annotations
import argparse, json, os, re, shutil, signal, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get('PHOSPHENE_URL', 'http://127.0.0.1:8198').rstrip('/')
OUTPUT_DIR = Path(os.environ.get('PHOSPHENE_OUTPUT_DIR', str(Path.home()/'AIStudio/outputs/video'))).expanduser()
TERMINAL = {'done', 'failed', 'cancelled', 'stopped', 'error'}

class ClientError(RuntimeError): pass

class PhospheneClient:
    def __init__(self, base_url=BASE_URL, timeout=20, poll_interval=15, opener=None, sleep=time.sleep):
        self.base_url=base_url.rstrip('/'); self.timeout=timeout; self.poll_interval=poll_interval
        self.open=opener or urllib.request.urlopen; self.sleep=sleep
    def request(self, path, data=None, timeout=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req=urllib.request.Request(self.base_url+path, data=body, headers={'Content-Type':'application/x-www-form-urlencoded'} if body else {})
        try:
            with self.open(req, timeout=timeout or self.timeout) as response: return response.read()
        except urllib.error.HTTPError as e:
            detail=e.read().decode(errors='replace')
            raise ClientError(f'Phosphene HTTP {e.code}: {detail}') from e
    def json(self,path,data=None):
        try: return json.loads(self.request(path,data))
        except (ValueError, TimeoutError, OSError) as e: raise ClientError(f'API request failed for {path}: {e}') from e
    def status(self): return self.json('/status')
    def submit(self, args):
        status=self.status()
        if status.get('current') or status.get('queue') or status.get('gpu',{}).get('busy'):
            raise ClientError('Phosphene reports an active render, queued job, or GPU holder; refusing to submit.')
        tier=status.get('tier',{}); maxdim=tier.get(args.mode+'_max_dim', 0)
        if not maxdim or max(args.width,args.height)>maxdim: raise ClientError(f"Installed tier does not support {args.mode} at these dimensions (max side {maxdim}).")
        if args.width%32 or args.height%32: raise ClientError('Width and height must be divisible by 32.')
        if args.frames%8!=1: raise ClientError('Frame count must satisfy frames % 8 == 1.')
        if args.mode=='i2v' and (not args.image or not Path(args.image).is_file()): raise ClientError('Image-to-video requires an existing input image.')
        if args.mode=='t2v' and args.image: raise ClientError('--image is only valid for i2v.')
        payload={'mode':args.mode,'engine':'ltx','prompt':args.prompt,'width':str(args.width),'height':str(args.height),'frames':str(args.frames),'frame_rate':'24','quality':args.quality,'seed':str(args.seed if args.seed is not None else -1),'enhance':'false','temporal_mode':'native','label':args.output_name}
        if args.mode=='i2v': payload['image']=str(Path(args.image).expanduser().resolve())
        known={j.get('id') for j in (status.get('queue') or [])}
        if status.get('current'): known.add(status['current'].get('id'))
        try: result=self.json('/queue/add',payload)
        except ClientError:
            # A dropped submit response is ambiguous: discover and stop any job
            # created after the clean preflight before allowing the lock to go.
            while True:
                try: after=self.status(); break
                except ClientError: self.sleep(self.poll_interval)
            possible=[j.get('id') for j in ([after.get('current')] if after.get('current') else [])+(after.get('queue') or []) if j.get('id') not in known]
            for jid in possible: self.cancel(jid)
            raise
        if not result.get('ok') or not result.get('id'): raise ClientError(f'Job submission rejected: {result}')
        return result['id']
    def wait(self, job_id, interrupt_event=None):
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            if interrupt_event and interrupt_event.is_set():
                self.cancel(job_id); raise ClientError('Interrupted; stop requested and awaiting server terminal state.')
            try: state=self.status()
            except ClientError:
                self.sleep(self.poll_interval)
                continue
            cur=state.get('current') or {}
            job=cur if cur.get('id')==job_id else next((j for j in state.get('history',[]) if j.get('id')==job_id),None)
            if not job:
                job=next((j for j in state.get('queue',[]) if j.get('id')==job_id),None)
            if job and job.get('status') in TERMINAL: return job
            self.sleep(self.poll_interval)
        self.cancel(job_id)
        raise ClientError(f'Timed out polling {job_id}; stop requested, continuing to hold scheduler lock until the server reports terminal status.')
    def cancel(self,job_id):
        try:
            state=self.status()
            if any(j.get('id')==job_id for j in (state.get('queue') or [])):
                self.request('/queue/remove',{'id':job_id})
            else: self.request('/stop?id='+urllib.parse.quote(job_id,safe=''))
        except ClientError:
            # A timeout or stale response is ambiguous; status confirmation below
            # is authoritative. Keep the scheduler process alive meanwhile.
            pass
        # Fail closed: the scheduler's lock is only useful while this process
        # remains alive. Keep polling without a deadline if stop is uncertain.
        while True:
            try: state=self.status()
            except ClientError:
                self.sleep(self.poll_interval)
                continue
            job=state.get('current') or {}
            if job.get('id')!=job_id:
                hist=next((j for j in state.get('history',[]) if j.get('id')==job_id),None)
                if hist and hist.get('status') in TERMINAL: return
                if not state.get('current') and not any(j.get('id')==job_id for j in state.get('queue',[])): return
            self.sleep(self.poll_interval)
    def download(self, server_path, target):
        url='/file?'+urllib.parse.urlencode({'path':server_path})
        data=self.request(url,timeout=max(self.timeout,120))
        if not data: raise ClientError('Downloaded MP4 is empty.')
        with target.open('xb') as f: f.write(data)

def safe_stem(s):
    s=re.sub(r'[^A-Za-z0-9_-]+','-',s).strip('-_')
    if not s: raise ClientError('Output name must contain letters or digits.')
    return s[:100]

def validate(path,ffprobe='ffprobe'):
    if not path.is_file() or path.stat().st_size==0: raise ClientError(f'Output missing or empty: {path}')
    try:
        p=subprocess.run([ffprobe,'-v','error','-show_entries','format=format_name,duration:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames','-of','json',str(path)],capture_output=True,text=True,timeout=30,check=True)
        info=json.loads(p.stdout)
    except (OSError,subprocess.SubprocessError,ValueError) as e: raise ClientError(f'ffprobe validation failed: {e}') from e
    if not any(s.get('codec_type')=='video' for s in info.get('streams',[])): raise ClientError('Downloaded file has no video stream.')
    return info

def generate(args,client=None,output_dir=OUTPUT_DIR,ffprobe='ffprobe'):
    client=client or PhospheneClient(timeout=args.job_timeout,poll_interval=args.poll_interval)
    output_dir=Path(output_dir).expanduser(); output_dir.mkdir(parents=True,exist_ok=True)
    stem=safe_stem(args.output_name); stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    video=output_dir/f'{stem}-{stamp}.mp4'; sidecar=video.with_suffix('.json')
    if video.exists() or sidecar.exists(): raise ClientError('Refusing to overwrite an existing output.')
    import threading
    interrupted=threading.Event(); old={}
    def handler(sig,frame): interrupted.set()
    for sig in (signal.SIGINT,signal.SIGTERM):
        old[sig]=signal.signal(sig,handler)
    started=time.monotonic(); job_id=None
    try:
        job_id=client.submit(args); job=client.wait(job_id,interrupted)
        if job.get('status')!='done': raise ClientError(f"Render {job_id} ended with {job.get('status')}: {job.get('error') or job.get('stopped_reason')}")
        server_path=job.get('output_path')
        if not server_path: raise ClientError('Completed job did not report output_path.')
        client.download(server_path,video)
        probe=validate(video,ffprobe)
        metadata={'job_id':job_id,'engine':'LTX-2.5 via Phosphene','mode':args.mode,'prompt':args.prompt,'quality':args.quality,'width':args.width,'height':args.height,'frames':args.frames,'frame_rate':24,'seed':args.seed if args.seed is not None else -1,'input_image':str(Path(args.image).expanduser().resolve()) if args.image else None,'server_output_path':server_path,'render_elapsed_sec':job.get('elapsed_sec'),'client_elapsed_sec':round(time.monotonic()-started,2),'completed_at':datetime.now(timezone.utc).isoformat(),'ffprobe':probe}
        with sidecar.open('x') as f: json.dump(metadata,f,indent=2)
        return video,sidecar,metadata
    except Exception:
        # Never leave an unvalidated/partial artifact that could be mistaken for success.
        if video.exists(): video.unlink()
        if sidecar.exists(): sidecar.unlink()
        raise
    finally:
        for sig,h in old.items(): signal.signal(sig,h)

def parser():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--mode',choices=['t2v','i2v'],default='t2v'); p.add_argument('--prompt',required=True); p.add_argument('--duration',type=float,help='Seconds; converted to nearest supported 8n+1 frame count'); p.add_argument('--frames',type=int); p.add_argument('--width',type=int,default=512); p.add_argument('--height',type=int,default=320); p.add_argument('--quality',choices=['quick','balanced','standard','high'],default='balanced'); p.add_argument('--seed',type=int); p.add_argument('--image'); p.add_argument('--output-name',required=True); p.add_argument('--job-timeout',type=float,default=3600); p.add_argument('--poll-interval',type=float,default=15); p.add_argument('--dry-run',action='store_true'); return p

def main(argv=None):
    args=parser().parse_args(argv)
    if args.frames is None:
        if args.duration is None: args.frames=121
        else: args.frames=max(9,round(args.duration*24/8)*8+1)
    if args.dry_run:
        print(json.dumps({'mode':args.mode,'frames':args.frames,'output_dir':str(OUTPUT_DIR),'scheduler':'~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py'})); return 0
    try:
        video,meta,data=generate(args); print(f"video={video}\nmetadata={meta}\nrender_elapsed_sec={data['render_elapsed_sec']}\nclient_elapsed_sec={data['client_elapsed_sec']}"); return 0
    except ClientError as e: print(f'phosphene-client: {e}',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
