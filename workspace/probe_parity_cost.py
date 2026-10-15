"""Native headed renderer submission and Chromium compositor trace, no inference."""
import base64,collections,json,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser,ROOT
OUT=ROOT/'workspace/evidence/parity'
def distribution(values):
 if not values:return None
 values=sorted(values);return {'count':len(values),'median':statistics.median(values),'p95':values[min(len(values)-1,int(len(values)*.95))],'max':max(values)}
def main():
 b=Browser('cost',headed=True);r={'scope':'Actual headed native Wayland app; current scale; no concurrent UI probes. Renderer fixture. Trace/CPU costs are not GPU durations or physical photon measurements.'};stream=None
 try:
  b.call('Page.bringToFront');time.sleep(.4)
  r['browser']=b.pipe.call('Browser.getVersion')['product'];r['viewport']=b.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})');complete={}
  def event(message):
   if message['method']=='Tracing.tracingComplete':complete.update(message['params'])
  b.pipe.on_event=event;b.pipe.call('Tracing.start',{'categories':'benchmark,cc,viz,devtools.timeline','transferMode':'ReturnAsStream','options':'record-as-much-as-possible'})
  for _ in range(3):
   b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.settle();b.key('Escape');b.wait('!hermesPaneMetrics.rafPending')
  before=b.evaluate('hermesPaneMetrics.frames');time.sleep(.6);r['idle_no_RAF']=b.evaluate('hermesPaneMetrics.frames')==before
  b.pipe.call('Tracing.end');deadline=time.monotonic()+8
  while not complete and time.monotonic()<deadline:b.evaluate('document.visibilityState');time.sleep(.02)
  stream=complete['stream'];data=bytearray()
  while True:
   chunk=b.pipe.call('IO.read',{'handle':stream,'size':65536});data.extend(base64.b64decode(chunk['data'])if chunk.get('base64Encoded')else chunk['data'].encode())
   if len(data)>64*1024*1024:raise RuntimeError('trace_size_limit')
   if chunk.get('eof'):break
  b.pipe.call('IO.close',{'handle':stream});stream=None;trace=json.loads(data);events=trace['traceEvents'];names=collections.Counter(e.get('name','')for e in events)
  relevant={n:c for n,c in names.items()if any(k in n.lower()for k in ['drawandswap','present','drawframe','beginframe'])}
  r['trace_event_counts']=relevant;r['compositor_CPU_duration_ms']={name:distribution([e['dur']/1000 for e in events if e.get('name')==name and e.get('ph')=='X' and 'dur'in e])for name in relevant if 'draw' in name.lower() or 'present' in name.lower()}
  r['WebGL']=b.evaluate("(()=>{const c=document.querySelector('.pane-flight-layer canvas'),g=c?.getContext('webgl2');if(!g)return null;const x=g.getExtension('WEBGL_debug_renderer_info');return {version:g.getParameter(g.VERSION),renderer:x?g.getParameter(x.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER),vendor:x?g.getParameter(x.UNMASKED_VENDOR_WEBGL):g.getParameter(g.VENDOR)}})()");r['renderer']=b.evaluate('hermesPaneMetrics');r['CPU_submit_ms']=distribution(r['renderer']['submitMs']);r['paint_ms']=distribution(r['renderer']['paintMs']);r['RAF_intervals_ms']=distribution(r['renderer']['frameIntervals']);r['runtime_errors']=b.evaluate('window.__parityErrors');r['served_assets']=b.served_hashes();r['status']='PASS scoped measurements'if r['idle_no_RAF']and not r['renderer']['fallbacks']and not r['runtime_errors']else'FAIL'
 finally:
  if stream:b.pipe.call('IO.close',{'handle':stream})
  (OUT/'cost.json').write_text(json.dumps(r,indent=2)+'\n');b.close()
if __name__=='__main__':main()
