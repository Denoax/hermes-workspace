"""Actual Wayland/compositor scale and native cursor mapping, with restoration guard."""
import json,os,re,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser,ROOT,FIXTURE
from workspace import launcher
OUT=ROOT/'workspace/evidence/parity'
def command(*args):return subprocess.check_output(args,text=True,timeout=6).strip()
def clients():return json.loads(command('hyprctl','clients','-j'))
def monitors():return json.loads(command('hyprctl','monitors','-j'))
def dispatch(code):return command('hyprctl','dispatch',code)

def main():
 OUT.mkdir(parents=True,exist_ok=True);b=Browser('compositor-final',headed=True);r={'scope':'Actual headed Brave Wayland window. Native compositor cursor/key injection is separate from physical human/device approval. No device-metrics emulation during scale trials.','scales':[],'checks':{},'model_calls':0};watchdog=None;original=None
 try:
  time.sleep(.5);client=next(c for c in clients() if launcher.owns_browser(c['pid']));address=client['address'];assert re.fullmatch(r'0x[0-9a-f]+',address)
  window='address:'+address;monitor=next(m for m in monitors() if m['id']==client['monitor']);original={k:monitor[k]for k in ['name','width','height','x','y','scale','refreshRate']}
  # Exact mode/position retained; no config files changed. Independently restore
  # this one output even if the browser/probe hangs or is interrupted.
  mode=f"{original['width']}x{original['height']}@{original['refreshRate']:.3f}"
  def rule(scale):return 'hl.monitor({output='+json.dumps(original['name'])+',mode='+json.dumps(mode)+',position='+json.dumps(str(original['x'])+'x'+str(original['y']))+',scale='+str(scale)+'})'
  restore=rule(original['scale'])
  watchdog=subprocess.Popen([sys.executable,'-c','import subprocess,time;time.sleep(110);subprocess.run(["hyprctl","eval",'+repr(restore)+'],timeout=6)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  b.evaluate("window.__nativeMove=null;addEventListener('pointermove',e=>window.__nativeMove={x:e.clientX,y:e.clientY,trusted:e.isTrusted,id:e.target.closest('button')?.id||null},true)")
  for scale in [1,1.25,1.5,2]:
   command('hyprctl','eval',rule(scale));time.sleep(.5);observed=next(m for m in monitors() if m['name']==original['name'])
   assert abs(observed['scale']-scale)<.01
   dispatch('hl.dsp.focus({window='+json.dumps(window)+'})')
   current=next(c for c in clients()if c['address']==address)
   if current.get('fullscreen'):dispatch('hl.dsp.window.fullscreen({window='+json.dumps(window)+',action="unset",mode="fullscreen"})')
   if not current.get('floating'):dispatch('hl.dsp.window.float({window='+json.dumps(window)+',action="toggle"})')
   dispatch('hl.dsp.window.resize({window='+json.dumps(window)+',x=910,y=500,relative=false})');dispatch('hl.dsp.window.center({window='+json.dumps(window)+'})');time.sleep(.45)
   client=next(c for c in clients() if c['address']==address)
   b.call('Page.bringToFront');time.sleep(.15)
   row={'native_window':{k:client[k]for k in ['at','size','floating','fullscreen','monitor']},'visibility':b.evaluate('({visible:document.visibilityState,focus:document.hasFocus()})'),'compositor_scale':observed['scale'],'Wayland':not client.get('xwayland'),'browser':b.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale,outer:[outerWidth,outerHeight]})'),'samples':[]}
   # Two actual native cursor moves calibrate client-decoration offset and
   # logical/CSS mapping. Readback comes from trusted pointermove events.
   # Hyprland's spring window animation outlives its reported goal geometry.
   # Calibrate only once two native/CSS maps agree at a unit slope; otherwise
   # moving client decorations create a false offset and apparent bad clicks.
   previous=None
   for attempt in range(24):
    native=[]
    for dx,dy in [(450,140),(530,220)]:
     gx=client['at'][0]+dx;gy=client['at'][1]+dy;dispatch(f'hl.dsp.cursor.move({{x={gx},y={gy}}})');time.sleep(.08);p=b.evaluate('window.__nativeMove')
     if not p:continue
     assert p['trusted'];native.append((gx,gy,p))
    if len(native)!=2:continue
    cx=native[1][2]['x']-native[0][2]['x'];cy=native[1][2]['y']-native[0][2]['y']
    if not cx or not cy:continue
    sx=80/cx;sy=80/cy;ox=native[0][0]-native[0][2]['x']*sx;oy=native[0][1]-native[0][2]['y']*sy
    current=[sx,sy,ox,oy]
    if abs(sx-1)<.015 and abs(sy-1)<.015 and previous and max(abs(a-c)for a,c in zip(previous,current))<1:break
    previous=current
   else:raise RuntimeError('native_window_mapping_did_not_stabilize')
   row['calibration_attempts']=attempt+1
   row['logical_units_per_CSS_pixel']=[sx,sy];rect=b.rect('#settings-toggle');r['scales'].append(row)
   for u in [.25,.5,.75]:
    for v in [.25,.5,.75]:
     x=rect['x']+rect['width']*u;y=rect['y']+rect['height']*v;dispatch(f'hl.dsp.cursor.move({{x={round(ox+x*sx)},y={round(oy+y*sy)}}})');time.sleep(.025);p=b.evaluate('window.__nativeMove');row['samples'].append({'u':u,'v':v,'trusted':p['trusted'],'target_is_settings':p['id']=='settings-toggle','CSS_error':[round(p['x']-x,3),round(p['y']-y,3)]})
   if not all(p['target_is_settings'] and max(map(abs,p['CSS_error']))<=1.5 for p in row['samples']):raise RuntimeError('native_pointer_alignment_failed')
   b.evaluate('window.__nativeClickStart=window.__parityEvents.length')
   for state in ['down','up']:dispatch('hl.dsp.send_key_state({window='+json.dumps(window)+',mods="",key="mouse:272",state='+json.dumps(state)+'})')
   row['pre_click_pointer']=b.evaluate('window.__nativeMove');row['click_events']=b.evaluate('window.__parityEvents.slice(__nativeClickStart)');b.wait("document.getElementById('appearance').open",timeout=3);b.settle();row['native_click']=b.evaluate("window.__parityEvents.slice(__nativeClickStart).some(e=>e.id==='settings-toggle'&&e.trusted)")
   b.capture(OUT/f'compositor-{int(scale*100)}.png');rect=b.rect('#appearance');b.capture(OUT/f'compositor-edge-{int(scale*100)}.png',{'x':rect['x'],'y':rect['y'],'width':rect['width'],'height':rect['height'],'scale':1})
   row['rest_geometry']=b.evaluate("({dialog:getComputedStyle(document.getElementById('appearance')).transform,close:getComputedStyle(document.querySelector('#appearance .pane-close')).transform})")
   b.key('Escape');b.wait("!document.querySelector('dialog[open]')");b.wait('!hermesPaneMetrics.rafPending');
  r['checks']['all_native_mapping']=all(s['native_click'] and all(p['trusted'] and p['target_is_settings'] and max(map(abs,p['CSS_error']))<=1.5 for p in s['samples'])for s in r['scales'])
  # The launcher uses app mode. Open a separate normal browser window in this
  # same private review profile to exercise a genuine browser tab becoming hidden.
  command('hyprctl','eval',restore);time.sleep(.4)
  target=b.pipe.call('Target.createTarget',{'url':launcher.ORIGIN+'/hermes-workspace','newWindow':True})['targetId']
  b.session=b.pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId'];b.call('Page.enable');b.call('Runtime.enable');b.call('Page.addScriptToEvaluateOnNewDocument',{'source':FIXTURE});b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'");b.call('Page.bringToFront');b.metric(1440,900)
  b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");time.sleep(.12)
  blank=b.pipe.call('Target.createTarget',{'url':'about:blank','newWindow':False})['targetId'];other=b.pipe.call('Target.attachToTarget',{'targetId':blank,'flatten':True})['sessionId'];b.pipe.call('Page.bringToFront',{},other);time.sleep(.15)
  r['hidden_readback']=b.evaluate("({visibility:document.visibilityState,raf:hermesPaneMetrics.rafPending,active:hermesPaneMetrics.active})")
  r['checks']['actual_hidden_tab_cleanup']=r['hidden_readback']=={'visibility':'hidden','raf':False,'active':0}
  b.pipe.call('Target.closeTarget',{'targetId':blank});b.call('Page.bringToFront');b.key('Escape')
  # Touch is explicitly emulated and reported separately from native pointer.
  b.metric(390,844,1);b.call('Emulation.setTouchEmulationEnabled',{'enabled':True,'maxTouchPoints':1});rect=b.rect('#settings-toggle');point={'x':rect['x']+rect['width']/2,'y':rect['y']+rect['height']/2}
  b.call('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point]});b.call('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});b.wait("document.getElementById('appearance').open");b.settle();r['checks']['touch_emulation_opens_settings']=True;b.key('Escape');b.call('Emulation.setTouchEmulationEnabled',{'enabled':False})
  r['served_assets']=b.served_hashes()
  r['status']='PASS' if all(r['checks'].values()) else 'FAIL'
 except Exception as error:
  r['status']='FAIL';r['error']=str(error);b.capture('/tmp/hermes-native-failure.png');raise
 finally:
  if original:
   command('hyprctl','eval',restore);time.sleep(.3);m=next(m for m in monitors() if m['name']==original['name']);r['restored']={k:m[k]for k in original};r['checks']['scale_and_position_restored']=m['scale']==original['scale'] and m['x']==original['x'] and m['y']==original['y']
   if r['checks']['scale_and_position_restored'] and watchdog:watchdog.terminate();watchdog.wait(timeout=3)
  (OUT/'native-compositor.json').write_text(json.dumps(r,indent=2)+'\n');b.close()

if __name__=='__main__':main()
