"""Authenticated loopback UI. Only fixed data operations reach the VM adapter."""
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from starter.json_limits import bounded_json
from workspace.catalog import Catalog,identifier

STATE=Path.home()/'.local/state/hermes-workspace'
PORT=18791
ORIGIN=f'http://127.0.0.1:{PORT}'
COOKIE='hermes_session'
_normal_pins={}


def normal_profile_unchanged():
    expected=json.loads((PROJECT/'configs/normal-profile.lock.json').read_text())
    try:
        for relative,digest in expected.items():
            path=Path.home()/relative;info=path.lstat()
            import stat
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():return False
            identity=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            previous=_normal_pins.get(relative)
            if previous is None or previous[0]!=identity:
                actual=hashlib.sha256(path.read_bytes()).hexdigest()
                after=path.lstat()
                if (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=identity:return False
                _normal_pins[relative]=(identity,actual)
            if _normal_pins[relative][1]!=digest:return False
        return True
    except OSError:return False


def historical_smoke():
    rows=[json.loads(line) for line in (PROJECT/'results/smoke/trials.jsonl').read_text().splitlines()]
    result={arm:{'correct':sum(r['passed'] is True for r in rows if r['arm']==arm),
                 'total':sum(r['arm']==arm for r in rows)} for arm in ('normal','abliterated')}
    return {**result,'matrix':'withheld_accuracy_gate','evidence_kind':'preserved_paired_guest_Hermes',
            'source':'results/smoke/trials.jsonl','historical':True}


def status():
    from lab.native_client import NativeClient,public_snapshot
    client=NativeClient(timeout=2)
    live=client.call('status') if client.available() else public_snapshot()
    normal=subprocess.run(['/usr/bin/systemctl','--user','show','manibot-llama.service','-p','ActiveState','--value'],capture_output=True,text=True,timeout=3)
    ready=False
    if normal.stdout.strip()=='active' and not live.get('observed_facts',{}).get('inference_window_active'):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=1) as r:health=json.load(r)
            with urllib.request.urlopen('http://127.0.0.1:8080/props',timeout=1) as r:props=json.load(r)
            ready=health.get('status')=='ok' and props.get('model_alias')=='qwen3.6-35b-a3b-q4' and props.get('default_generation_settings',{}).get('n_ctx')==65536 and normal_profile_unchanged()
        except (OSError,ValueError):pass
    return {'native':live,'normal_model_available':ready,
            'last_smoke':historical_smoke(),
            'broker_version':live.get('broker_version'),'tool_profile':live.get('tool_profile','not_installed')}


class BoundedServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(12)
        super().__init__(*args,**kwargs)

    def process_request(self,request,address):
        if not self.slots.acquire(False):self.shutdown_request(request);return
        super().process_request(request,address)

    def process_request_thread(self,*args):
        try:super().process_request_thread(*args)
        finally:self.slots.release()


class Application:
    def __init__(self,root):
        self.catalog=Catalog(root)
        self.csrf=secrets.token_urlsafe(32)
        self.sessions={}
        self.rate={}
        self.lock=threading.RLock()

    def call(self,method,fields):
        contracts={'status.read':set(),'homebrew.open':set(),'workspace.list':set(),'workspace.create':{'label'},
          'workspace.files':{'project_id'},'workspace.file.read':{'project_id','relative_path'},
          'workspace.file.write':{'project_id','relative_path','text','expected_sha256'},
          'workspace.import.request':{'project_id'},'workspace.import.commit':{'project_id','ticket'},
          'workspace.open':{'project_id'},'session.list':set(),'session.create':{'project_id','arm'},
          'session.rename':{'session_id','title'},'view.read':set(),'view.write':{'state'},
          'draft.read':{'session_id'},'draft.write':{'session_id','text','mode'},'session.history':{'session_id'},'session.jobs':{'session_id'},'window.request':set(),
          'job.submit':{'session_id','client_job_id','prompt','snapshot_sha256','task_kind'},
          'job.read':{'job_id'},'job.cancel':{'job_id'},'artifact.read':{'job_id','artifact_id'},
          'patch.prepare':{'job_id'},'patch.apply':{'review_ticket'}}
        if method not in contracts or set(fields)!=contracts[method]:raise ValueError('unknown_method_or_fields')
        c=self.catalog
        if method=='status.read':return status()
        if method=='homebrew.open':
            if not status()['normal_model_available']:raise RuntimeError('Normal Qwen is paused; wait for verified recovery.')
            subprocess.Popen(['/usr/bin/kitty','--title','Hermes Homebrew','/home/mani/.local/bin/hermes'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return {'opened':True,'context':'existing_normal_Hermes_profile'}
        if method=='workspace.list':return c.projects()
        if method=='workspace.create':return c.create(fields['label'])
        if method.startswith('workspace.file'):
            fs=c.files(fields['project_id'])
            try:
                if method=='workspace.files':
                    tree=fs.tree()
                    try:snapshot=c.snapshot(fields['project_id'])['sha256'];reason=None
                    except ValueError:snapshot=None;reason='Stage at most 16 text files / 32 KiB for a job.'
                    return {'files':tree,'snapshot_sha256':snapshot,'job_eligibility_reason':reason}
                if method=='workspace.file.read':return fs.read(fields['relative_path'])
                if method=='workspace.file.write':return fs.write(fields['relative_path'],fields['text'],fields['expected_sha256'])
            finally:fs.close()
        if method=='workspace.import.request':
            c.files(fields['project_id']).close()
            result=subprocess.run(['/usr/bin/kdialog','--getexistingdirectory',str(Path.home()),'Select files to copy into Hermes Lab'],capture_output=True,text=True,timeout=120)
            if result.returncode:return {'cancelled':True}
            return c.import_preview(fields['project_id'],result.stdout.strip())
        if method=='workspace.import.commit':return c.import_commit(fields['project_id'],fields['ticket'])
        if method=='workspace.open':
            c.files(fields['project_id']).close()
            subprocess.Popen(['/usr/bin/dolphin',str(c.root/'projects'/fields['project_id']/'workspace')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return {'opened':True}
        if method=='session.list':return c.sessions()
        if method=='session.create':return c.session(fields['project_id'],fields['arm'])
        if method=='session.rename':return c.rename(fields['session_id'],fields['title'])
        if method=='view.read':return c.view()
        if method=='view.write':return c.save_view(fields['state'])
        if method=='draft.read':return c.draft(fields['session_id'])
        if method=='draft.write':return c.save_draft(fields['session_id'],fields['text'],fields['mode'])
        if method=='session.history':return c.history(fields['session_id'])
        if method=='session.jobs':
            c.session_record(fields['session_id'])
            with c.lock:
                return [{'id':row[0],'state':row[1]} for row in c.db.execute('SELECT id,state FROM jobs WHERE session=? ORDER BY rowid',(fields['session_id'],)).fetchall()]
        if method=='window.request':
            return {'starts_window':False,'duration_seconds':1800,'normal_Qwen_paused':True,
                    'command':'sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/workspace_acceptance.py run',
                    'message':'A new 30-minute Lab window pauses normal Qwen and restores it automatically. Run the prepared native command only after setup is installed.'}
        from workspace.jobs import Jobs
        return Jobs(c).call(method,fields)


def handler(app,credential):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def log_message(self,*args):pass
        def setup(self):super().setup();self.connection.settimeout(5)
        def reply(self,code,data,mime='application/json'):
            raw=json.dumps(data,allow_nan=False).encode() if mime=='application/json' else data
            if len(raw)>2*1024*1024:
                code=413;raw=b'{"error":"response_limit"}';mime='application/json'
            self.send_response(code)
            for key,value in {'Content-Type':mime,'Content-Length':str(len(raw)),'Cache-Control':'no-store',
                 'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(raw)
        def host_allowed(self):return self.headers.get_all('Host',[])==[f'127.0.0.1:{PORT}']
        def authenticated(self):
            try:
                cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
                return COOKIE in cookies and secrets.compare_digest(cookies[COOKIE].value,credential)
            except Exception:return False
        def do_GET(self):
            if not self.host_allowed() or self.headers.get('Origin',ORIGIN)!=ORIGIN:
                self.reply(403,{'error':'local_origin_required'});return
            if self.path=='/health':self.reply(200,{'application':'hermes-workspace','view_only':True});return
            if self.path=='/hermes-workspace/api/bootstrap':
                if not self.authenticated():self.reply(401,{'error':'Open Hermes from Applications to connect securely.'});return
                self.reply(200,{'csrf':app.csrf,'version':1});return
            assets={'/':'index.html','/hermes-workspace':'index.html','/style.css':'style.css','/portfolio.css':'portfolio.css','/app.js':'app.js'}
            for module in ('icons','pane-motion','portfolio-nav','interface-audio','flight-kernel','paintPane','glassOptics','sliderFlight','portfolio-settings','paint-support'):
                assets['/'+module+'.mjs']=module+'.mjs'
            assets['/brand/hermes.png']='brand/hermes.png'
            assets['/fonts/Inter-Medium.woff2']='fonts/Inter-Medium.woff2'
            assets['/fonts/Rubik.ttf']='fonts/Rubik.ttf'
            for sound in ('soft-press','soft-close'):
                assets['/sounds/'+sound+'.wav']='sounds/'+sound+'.wav'
            for font in ('BebasNeue','DMSans','SixCaps'):
                assets['/fonts/'+font+'.ttf']='fonts/'+font+'.ttf'
            if self.path not in assets:self.reply(404,{'error':'not_found'});return
            name=assets[self.path]
            mime=('image/png' if name.endswith('.png') else 'font/ttf' if name.endswith('.ttf') else 'font/woff2' if name.endswith('.woff2') else 'audio/wav' if name.endswith('.wav') else 'text/javascript; charset=utf-8' if name.endswith(('.js','.mjs')) else 'text/css; charset=utf-8' if name.endswith('.css') else 'text/html; charset=utf-8')
            self.reply(200,(PROJECT/'workspace/ui'/name).read_bytes(),mime)
        def do_POST(self):
            if self.path!='/hermes-workspace/api/rpc' or not self.host_allowed() or self.headers.get_all('Origin',[])!=[ORIGIN]:
                self.reply(403,{'error':'local_origin_required'});return
            if not self.authenticated() or not secrets.compare_digest(self.headers.get('X-Hermes-CSRF','').encode(),app.csrf.encode()):
                self.reply(403,{'error':'session_or_CSRF_denied'});return
            if self.headers.get('Transfer-Encoding') or self.headers.get_all('Content-Type',[])!=['application/json']:
                self.reply(400,{'error':'bounded_JSON_required'});return
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=65536:
                self.reply(413,{'error':'body_limit'});return
            with app.lock:
                now=time.monotonic();recent=[t for t in app.rate.get('local',[]) if now-t<1]
                if len(recent)>=20:self.reply(429,{'error':'rate_limit'});return
                app.rate['local']=[*recent,now]
            try:
                data=bounded_json(self.rfile.read(int(lengths[0])),max_bytes=65536)
                if type(data) is not dict or set(data)!={'version','method','fields'} or type(data['version']) is not int or data['version']!=1 or type(data['method']) is not str or type(data['fields']) is not dict:
                    raise ValueError('unsupported_RPC_contract')
                value=app.call(data['method'],data['fields']);self.reply(200,{'result':value})
            except (OSError,ValueError,RuntimeError,PermissionError,subprocess.SubprocessError,sqlite3.Error) as error:
                code=str(error) if isinstance(error,(ValueError,RuntimeError)) and len(str(error))<200 else type(error).__name__
                self.reply(409,{'error':code})
        def do_PUT(self):self.reply(405,{'error':'method_denied'})
        def do_DELETE(self):self.reply(405,{'error':'method_denied'})
    return Handler


def main():
    if os.geteuid()==0:raise SystemExit('UI must run as normal user')
    os.umask(0o077);STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if STATE.is_symlink() or STATE.stat().st_mode&0o077:raise PermissionError('private_UI_state_required')
    key=STATE/'client-cookie'
    if key.exists():credential=key.read_text().strip()
    else:
        credential=secrets.token_urlsafe(32)
        with key.open('x') as out:out.write(credential)
        key.chmod(0o600)
    if key.is_symlink() or key.stat().st_uid!=os.getuid() or key.stat().st_mode&0o077:raise PermissionError('private_credential_required')
    app=Application(Path.home()/'HermesLab')
    server=BoundedServer(('127.0.0.1',PORT),handler(app,credential))
    (STATE/'endpoint.json').write_text(json.dumps({'origin':ORIGIN,'PID':os.getpid(),'version':1}))
    server.serve_forever(poll_interval=.25)


if __name__=='__main__':main()
