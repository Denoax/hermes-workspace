"""Timestamp-preserving browser review recording; no interpolation or cuts."""
import base64,json,os,subprocess,tempfile,time
from pathlib import Path


class Recording:
    def __init__(self,browser,output):
        self.browser=browser;self.output=Path(output);self.temporary=tempfile.TemporaryDirectory(prefix='hermes-motion-');self.frames=[];self.previous=browser.pipe.on_event
        def event(message):
            if message.get('method')=='Page.screencastFrame':
                p=message['params'];path=Path(self.temporary.name)/f'{len(self.frames):06d}.jpg';path.write_bytes(base64.b64decode(p['data']));self.frames.append((path,p['metadata']['timestamp']))
                browser.pipe.counter+=1;raw=json.dumps({'id':browser.pipe.counter,'method':'Page.screencastFrameAck','params':{'sessionId':p['sessionId']},'sessionId':browser.session}).encode()+b'\0'
                while raw:raw=raw[os.write(browser.pipe.write,raw):]
            elif self.previous:self.previous(message)
        browser.pipe.on_event=event;browser.call('Page.startScreencast',{'format':'jpeg','quality':91,'maxWidth':1440,'maxHeight':900,'everyNthFrame':1})
    def hold(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.browser.evaluate('document.visibilityState');time.sleep(.02)
    def finish(self):
        self.browser.call('Page.stopScreencast');self.browser.pipe.on_event=self.previous
        try:
            rows=[]
            for i,(path,stamp) in enumerate(self.frames):
                rows.append("file '"+str(path)+"'")
                if i+1<len(self.frames):rows.append('duration '+str(max(.001,self.frames[i+1][1]-stamp)))
            rows.append("file '"+str(self.frames[-1][0])+"'");concat=Path(self.temporary.name)/'frames.txt';concat.write_text('\n'.join(rows)+'\n')
            subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-fps_mode','vfr','-c:v','libx264','-crf','20','-pix_fmt','yuv420p',str(self.output)],check=True,timeout=60)
            return {'frames':len(self.frames),'seconds':self.frames[-1][1]-self.frames[0][1],'clock':'original CDP timestamps, VFR, no cuts/interpolation/speed changes','audio':'silent recording; accepted sample identity/cue checks are separate','GPU_timings':'unmeasured'}
        finally:self.temporary.cleanup()
