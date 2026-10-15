"""Private-pipe native browser harness. Never exports cookies, text or RPC payloads."""
import base64,json,os,sys,time,hashlib,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workspace import launcher

# Isolated, explicitly labelled renderer data, never inserted into the catalog.
FIXTURE=r'''(() => {
const original=window.fetch.bind(window), pid='a'.repeat(32),sid='b'.repeat(32);
const view={project_id:pid,session_id:sid,file_path:null,editor:null,files_open:false,arm:'normal',task_kind:'chat',theme:'dark',motion:'system'};
const replies={
 'workspace.list':[{id:pid,label:'Review fixture'},{id:'c'.repeat(32),label:'Source examples'}],
 'session.list':[{id:sid,project:pid,title:'Interface review',arm:'normal'}],
 'view.read':view,'view.write':true,'draft.read':{text:'',mode:'chat'},'draft.write':true,'session.jobs':[],
 'workspace.files':{files:['program.py','src/main.cpp'],snapshot_sha256:'d'.repeat(64)},
 'workspace.file.read':{text:'# Renderer fixture only\nprint("Hermes")\n',sha256:'e'.repeat(64)},
 'session.history':[{role:'user',text:'Review [program.py](program.py). Keep the original files.'},{role:'assistant',text:'Renderer fixture only. No model response.\n\n```python\ndef clamp(value):\n    return min(100, max(0, value))\n```\nLiteral text: <img src=x onerror=window.__xss=1>'},{role:'event',text:'read_file fixture\nNo host or guest task was executed.'}]
};
window.fetch=async(url,options)=>{if(String(url).endsWith('/api/rpc')){const q=JSON.parse(options.body);if(q.method in replies)return new Response(JSON.stringify({result:replies[q.method]}),{status:200});if(q.method!=='status.read')return new Response(JSON.stringify({error:'renderer_fixture_blocks_mutation'}),{status:409});}return original(url,options);};
for(const kind of ['pointerdown','pointerup'])document.addEventListener(kind,e=>{if(window.__guardParityClick){e.preventDefault();e.stopImmediatePropagation();}},true);
document.addEventListener('change',e=>{if(window.__guardParityChange){e.preventDefault();e.stopImmediatePropagation();}},true);
window.__parityEvents=[];document.addEventListener('click',e=>{const b=e.target.closest('button,input,select,textarea,a,summary,label.motion-switch');if(b)window.__parityEvents.push({id:b.id||b.dataset.probe,trusted:e.isTrusted});if(window.__guardParityClick){e.preventDefault();e.stopImmediatePropagation();}},true);
window.__parityErrors=[];window.addEventListener('error',()=>__parityErrors.push('runtime_error'));window.addEventListener('unhandledrejection',()=>__parityErrors.push('unhandled_rejection'));
document.addEventListener('DOMContentLoaded',()=>{const banner=document.createElement('span');banner.id='fixture-watermark';banner.textContent='Renderer fixture · no model or native job';banner.style.cssText='position:fixed;bottom:4px;left:12px;font:11px sans-serif;color:#88939d;pointer-events:none;z-index:100';document.body.append(banner);});
})()'''

class Browser:
 def __init__(self,profile='parity',headed=False,fixture=True,audio_sink=None,quiet=False):
  launcher.PROFILE=launcher.PROFILE.parent/('hermes-'+profile+'-review')
  self.audio_module=None
  if quiet and audio_sink is None:
   import subprocess
   audio_sink='hermes_parity_'+os.urandom(5).hex()
   self.audio_module=subprocess.check_output(['/usr/bin/pactl','load-module','module-null-sink','sink_name='+audio_sink],text=True).strip()
  try:self.pipe,self.process=launcher.browser(headless=not headed,audio_sink=audio_sink)
  except BaseException:
   if self.audio_module:
    import subprocess
    subprocess.run(['/usr/bin/pactl','unload-module',self.audio_module],check=True,timeout=5)
   raise
  target=next(x for x in self.pipe.call('Target.getTargets')['targetInfos'] if x.get('type')=='page' and x.get('url','').startswith(launcher.ORIGIN))
  self.target=target['targetId'];self.session=self.pipe.call('Target.attachToTarget',{'targetId':self.target,'flatten':True})['sessionId']
  self.call('Page.enable');self.call('Runtime.enable');self.call('Performance.enable')
  if fixture:self.call('Page.addScriptToEvaluateOnNewDocument',{'source':FIXTURE});self.call('Page.reload')
  try:
   self.wait("document.getElementById('connection')?.textContent==='Connected'")
   self.evaluate('document.fonts.ready');time.sleep(.15)
  except BaseException:
   self.close();raise
 def call(self,method,params=None):return self.pipe.call(method,params,self.session)
 def evaluate(self,source):
  r=self.call('Runtime.evaluate',{'expression':source,'returnByValue':True,'awaitPromise':True})
  if r.get('exceptionDetails'):raise RuntimeError('parity_evaluation_failed:'+r['exceptionDetails'].get('text',''))
  return r.get('result',{}).get('value')
 def wait(self,source,timeout=12):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   if self.evaluate(source):return
   time.sleep(.025)
  raise RuntimeError('parity_state_timeout:'+source)
 def settle(self):self.wait("[...document.querySelectorAll('dialog[open]')].every(d=>d.dataset.flight==='settled') && !globalThis.hermesPaneMetrics?.rafPending")
 def key(self,key,code=None,modifiers=0):
  virtual={'Enter':13,'Escape':27,'Tab':9,'Backspace':8,'ArrowLeft':37,'ArrowUp':38,'ArrowRight':39,'ArrowDown':40}.get(key,ord(key.upper()) if len(key)==1 else 0)
  for kind in ['keyDown','keyUp']:
   fields={'type':kind,'key':key,'code':code or key,'modifiers':modifiers,'windowsVirtualKeyCode':virtual}
   if kind=='keyDown' and key=='Enter':fields['text']='\r';fields['unmodifiedText']='\r'
   self.call('Input.dispatchKeyEvent',fields)
 def rect(self,selector):return self.evaluate('document.querySelector('+json.dumps(selector)+').getBoundingClientRect().toJSON()')
 def click(self,selector,guard=False):
  r=self.rect(selector);self.mouse(r['x']+r['width']/2,r['y']+r['height']/2,guard)
 def dialog_click(self,selector,text):
  # A native JS dialog blocks the mouse-release reply. Handle its protocol
  # event without making a reentrant Pipe.call that would consume that reply.
  previous=self.pipe.on_event
  def event(message):
   if message.get('method')=='Page.javascriptDialogOpening':
    self.pipe.counter+=1;raw=json.dumps({'id':self.pipe.counter,'method':'Page.handleJavaScriptDialog','params':{'accept':True,'promptText':text},'sessionId':self.session}).encode()+b'\0'
    while raw:raw=raw[os.write(self.pipe.write,raw):]
   elif previous:previous(message)
  self.pipe.on_event=event
  try:self.click(selector)
  finally:self.pipe.on_event=previous
 def mouse(self,x,y,guard=False):
  if guard:self.evaluate('window.__guardParityClick=true')
  try:
   self.call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':x,'y':y})
   self.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':x,'y':y,'button':'left','clickCount':1})
   self.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1})
  finally:
   if guard:self.evaluate('window.__guardParityClick=false')
 def metric(self,width,height,dpr=1):self.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':dpr,'mobile':width<600});time.sleep(.08)
 def capture(self,path,clip=None):
  p={'format':'png'}
  if clip:p['clip']=clip
  Path(path).write_bytes(base64.b64decode(self.call('Page.captureScreenshot',p)['data']))
 def served_hashes(self):
  names=['index.html','app.js','style.css','portfolio.css','brand/hermes.png']+[n+'.mjs'for n in ['icons','pane-motion','portfolio-nav','interface-audio','flight-kernel','paintPane','glassOptics','sliderFlight','portfolio-settings','paint-support']]+['fonts/'+n for n in ['Inter-Medium.woff2','Rubik.ttf','BebasNeue.ttf','DMSans.ttf','SixCaps.ttf']]+['sounds/'+n+'.wav'for n in ['soft-press','soft-close']]
  hashes={}
  for name in names:
   route='/hermes-workspace'if name=='index.html'else'/'+name
   with urllib.request.urlopen(launcher.ORIGIN+route,timeout=3)as response:data=response.read()
   if data!=(ROOT/'workspace/ui'/name).read_bytes():raise AssertionError('served_source_drift')
   hashes[name]=hashlib.sha256(data).hexdigest()
  return hashes
 def close(self):
  try:self.pipe.call('Browser.close')
  except (OSError,RuntimeError):pass
  try:self.process.wait(timeout=5)
  except Exception:self.process.terminate();self.process.wait(timeout=5)
  for fd in [self.pipe.read,self.pipe.write]:
   try:os.close(fd)
   except OSError:pass
  if self.audio_module:
   import subprocess
   subprocess.run(['/usr/bin/pactl','unload-module',self.audio_module],check=True,timeout=5);self.audio_module=None
