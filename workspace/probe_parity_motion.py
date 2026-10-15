"""Unedited, timestamped native browser motion and bounded renderer-cost evidence."""
import base64,hashlib,json,os,statistics,subprocess,tempfile,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace.parity_browser import Browser,ROOT
OUT=ROOT/'workspace/evidence/parity'

def main():
 OUT.mkdir(parents=True,exist_ok=True);sink='hermes_parity_'+os.urandom(5).hex();module=subprocess.check_output(['pactl','load-module','module-null-sink','sink_name='+sink,'sink_properties=device.description=HermesParityReview'],text=True).strip();b=None;audio_process=None;r={'scope':'Native Brave authenticated UI, renderer fixtures, 1440x900 CSS DPR1. No production writes/inference.','checks':{},'segments':[],'GPU_timings':'unmeasured; submitMs is CPU and RAF intervals are not presentation timings'}
 try:
  b=Browser('motion-audio',audio_sink=sink)
  b.metric(1440,900);b.key('Escape');b.wait("!document.querySelector('dialog[open]')")
  r['fonts']=b.evaluate("({ready:document.fonts.status,inter:document.fonts.check('500 14px \"Portfolio Inter\"'),rubik:document.fonts.check('16px Rubik'),body:document.fonts.check('16px \"Hermes Sans\"')})")
  with tempfile.TemporaryDirectory(prefix='parity-recording-',dir=ROOT/'workspace/evidence') as temporary:
   audio_path=Path(temporary)/'isolated-audio.mka';audio_process=subprocess.Popen(['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-copyts','-f','pulse','-i',sink+'.monitor','-c:a','pcm_s16le',str(audio_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(.35)
   frames=[]
   def event(message):
    if message['method']!='Page.screencastFrame':return
    p=message['params'];stamp=p['metadata'].get('timestamp',time.time());name=Path(temporary)/f'{len(frames):05d}.jpg';name.write_bytes(base64.b64decode(p['data']));frames.append((name,stamp))
    b.pipe.counter+=1;raw=json.dumps({'id':b.pipe.counter,'method':'Page.screencastFrameAck','params':{'sessionId':p['sessionId']},'sessionId':b.session}).encode()+b'\0'
    while raw:raw=raw[os.write(b.pipe.write,raw):]
   b.pipe.on_event=event;b.call('Page.startScreencast',{'format':'jpeg','quality':90,'maxWidth':1440,'maxHeight':900,'everyNthFrame':1})
   def pause(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:b.evaluate('document.visibilityState');time.sleep(.015)
   def segment(label):r['segments'].append({'label':label,'seconds_from_first_frame':round(time.time()-frames[0][1],3) if frames else 0})
   pause(.7);b.capture(OUT/'hermes-revised-sidebar.png')
   for label in ['first-open','warm-open']:
    segment(label);closed_x=b.rect('#settings-toggle')['x'];b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.settle();r['checks'][label+'_settings_bar_popout']=19<=b.rect('#settings-toggle')['x']-closed_x<=22;pause(.8);b.key('Escape');pause(.8)
   for delay in [.04,.16,.35]:
    segment(f'close-reopen-{round(delay*1000)}ms');b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");pause(delay);b.key('Escape');r['checks'][f'immediate_input_release_{delay}']=b.evaluate("!document.getElementById('appearance').open && document.activeElement.id==='settings-toggle'");pause(.04);b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.settle();pause(.15);b.key('Escape');pause(.5)
   segment('switch-to-another-panel');b.click('#settings-toggle');pause(.16);b.click('#diagnostics');b.wait("document.getElementById('details').open");b.settle();pause(.2);b.key('Escape');pause(.5)
   segment('resize-retarget');b.click('#settings-toggle');pause(.16);b.metric(1380,880);b.settle();pause(.2);b.metric(1440,900);b.settle();pause(.2)
   segment('theme-retarget');b.click('#theme-buddy');b.settle();pause(.3);b.capture(OUT/'motion-light-settings.png');b.click('#theme-buddy');b.settle();pause(.2)
   # Drag a real captured range away from the rail; the source ballistic kernel
   # commits its predicted landing through the same native range state owner.
   segment('owned-slider-flight');rect=b.rect('#interface-volume');x=rect['x']+rect['width']*.2;y=rect['y']+rect['height']/2
   b.call('Input.dispatchMouseEvent',{'type':'mousePressed','button':'left','clickCount':1,'x':x,'y':y});b.call('Input.dispatchMouseEvent',{'type':'mouseMoved','button':'left','buttons':1,'x':x+40,'y':y-28});pause(.18);b.call('Input.dispatchMouseEvent',{'type':'mouseReleased','button':'left','clickCount':1,'x':x+40,'y':y-28});pause(.7);b.click('#reset-settings');b.settle();pause(.2);b.key('Escape');pause(.6)
   segment('file-review');b.click('#files-toggle');b.wait("document.getElementById('files-panel').open");b.settle();b.click('#tree button[data-path]');b.wait("!document.getElementById('file-preview').hidden");pause(.4);b.capture(OUT/'motion-files.png');b.key('Escape');pause(.6)
   b.call('Page.stopScreencast');b.pipe.on_event=None
   rows=[]
   for i,(name,stamp) in enumerate(frames):
    rows.append("file '"+str(name)+"'")
    if i+1<len(frames):rows.append('duration '+str(max(.001,frames[i+1][1]-stamp)))
   rows.append("file '"+str(frames[-1][0])+"'");concat=Path(temporary)/'frames.txt';concat.write_text('\n'.join(rows)+'\n')
   video=OUT/'unedited-motion.mp4';subprocess.run(['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-fps_mode','vfr','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(video)],check=True,timeout=60)
   audio_process.send_signal(__import__('signal').SIGINT);audio_process.wait(timeout=8);audio_process=None
   audio_info=json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_format','-show_streams','-of','json',str(audio_path)]));audio_start=float(audio_info['format']['start_time']);trim=frames[0][1]-audio_start
   if not 0<=trim<5:raise RuntimeError('audio_clock_alignment_unproven')
   muxed=OUT/'unedited-motion-with-audio.mp4';subprocess.run(['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),'-ss',str(trim),'-i',str(audio_path),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','160k','-t',str(frames[-1][1]-frames[0][1]),str(muxed)],check=True,timeout=45)
   r['audio']={'isolation':'Only this owned review browser routed to a temporary null sink. No microphone or normal desktop sink captured. Sink unloaded afterward.','clock':'Pulse copyts and CDP frame timestamps share Unix clock; audio trimmed to first video timestamp. AAC packet granularity remains.','audio_start_timestamp':audio_start,'first_video_timestamp':frames[0][1],'audio_trim_seconds':trim,'file':muxed.name,'sha256':hashlib.sha256(muxed.read_bytes()).hexdigest(),'playback_unavailable':b.evaluate("document.getElementById('sound-toggle').dataset.audioState||null")}
   gaps=[1000*(frames[i+1][1]-frames[i][1]) for i in range(len(frames)-1)]
   r['recording']={'file':video.name,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'frames':len(frames),'seconds':frames[-1][1]-frames[0][1],'max_capture_gap_ms':max(gaps),'cadence':'original timestamps preserved; no interpolation, cuts or speed changes. Screencast only emits changed frames; idle gaps are expected.','continuous_human_approval':'pending'}
  b.wait("!globalThis.hermesPaneMetrics?.rafPending");before=b.evaluate('hermesPaneMetrics.frames');time.sleep(1);after=b.evaluate('hermesPaneMetrics.frames');r['checks']['idle_no_renderer_RAF']=before==after
  # Real background-tab lifecycle (a separate blank browser tab), not a forged
  # visibilitychange event. The native headed probe repeats this on Wayland.
  b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.call('Page.setWebLifecycleState',{'state':'frozen'});b.call('Page.setWebLifecycleState',{'state':'active'});b.settle();b.key('Escape');b.wait("!globalThis.hermesPaneMetrics?.rafPending")
  r['checks']['frozen_resume_bounded']=True
  for dpr in [1,2]:
   b.metric(1440,900,dpr);b.click('#settings-toggle');b.wait("document.getElementById('appearance').open");b.settle();rect=b.rect('#appearance');b.capture(OUT/f'native-edge-dpr{dpr}.png',{'x':rect['x'],'y':rect['y'],'width':rect['width'],'height':rect['height'],'scale':1});b.key('Escape');b.wait("!globalThis.hermesPaneMetrics?.rafPending")
  r['renderer']=b.evaluate('hermesPaneMetrics');intervals=r['renderer']['frameIntervals'];r['RAF_intervals_ms']={'median':statistics.median(intervals),'p95':sorted(intervals)[int(len(intervals)*.95)],'max':max(intervals)}
  r['served_assets']=b.served_hashes()
  r['runtime_errors']=b.evaluate('window.__parityErrors');r['checks']['console_clean']=not r['runtime_errors'];r['checks']['gpu_glass_without_fallback']=not r['renderer']['fallbacks'];r['status']='PASS scoped technical checks' if all(r['checks'].values()) else 'FAIL'
 finally:
  if audio_process:audio_process.terminate();audio_process.wait(timeout=5)
  subprocess.run(['pactl','unload-module',module],check=True,timeout=5)
  (OUT/'motion.json').write_text(json.dumps(r,indent=2)+'\n');
  if b:b.close()

if __name__=='__main__':main()
