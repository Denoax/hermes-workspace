"""Real native Brave CDP UI checks; no model, receipt or job is simulated."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workspace import launcher


def main():
    if os.geteuid()==0:raise SystemExit('normal-user UI probe only')
    evidence=ROOT/'workspace/evidence';evidence.mkdir(exist_ok=True)
    launcher.PROFILE=launcher.PROFILE.parent/'hermes-workspace-probe'
    pipe,process=launcher.browser(headless=True)
    record={'evidence_kind':'actual_native_Brave_authenticated_UI','checks':{},'model_calls':0,'GPU_window_opened':False}
    try:
        target=next(x for x in pipe.call('Target.getTargets')['targetInfos'] if x.get('type')=='page' and x.get('url','').startswith(launcher.ORIGIN))
        session=pipe.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})['sessionId']
        pipe.call('Page.enable',{},session)
        pipe.call('Runtime.enable',{},session)
        def evaluate(code):
            result=pipe.call('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True},session)
            if result.get('exceptionDetails'):raise RuntimeError('UI evaluation failed: '+result['exceptionDetails']['text'])
            return result.get('result',{}).get('value')
        def wait(code):
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                if evaluate(code):return
                time.sleep(.15)
            raise RuntimeError('UI state deadline: '+code)
        def metric(width,height):pipe.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<600},session)
        def screenshot(name):
            data=base64.b64decode(pipe.call('Page.captureScreenshot',{'format':'png'},session)['data'])
            (evidence/name).write_bytes(data);return hashlib.sha256(data).hexdigest()
        metric(1440,900);wait("document.getElementById('connection').textContent.includes('connected')")
        record['checks']['authenticated']=True
        record['captures']={'authenticated-idle-desktop.png':screenshot('authenticated-idle-desktop.png')}
        with tempfile.TemporaryDirectory(prefix='hermes-ui-recording-',dir=str(launcher.STATE)) as directory:
            frames=[]
            def event(message):
                if message['method']!='Page.screencastFrame':return
                value=message['params'];timestamp=value['metadata'].get('timestamp',time.time())
                name=Path(directory)/('%04d.jpg'%len(frames))
                name.write_bytes(base64.b64decode(value['data']));frames.append((name,timestamp))
                pipe.counter+=1
                ack={'id':pipe.counter,'method':'Page.screencastFrameAck','params':{'sessionId':value['sessionId']},'sessionId':session}
                raw=json.dumps(ack).encode()+b'\0'
                while raw:raw=raw[os.write(pipe.write,raw):]
            pipe.on_event=event
            pipe.call('Page.startScreencast',{'format':'jpeg','quality':85,'maxWidth':1440,'maxHeight':900,'everyNthFrame':1},session)
            label='Owned UI review '+time.strftime('%H%M%S',time.gmtime())
            evaluate("window.prompt=()=>"+json.dumps(label)+";document.getElementById('new-project').click()")
            wait("document.getElementById('project-label').textContent==="+json.dumps(label))
            evaluate("window.prompt=()=> 'program.py';document.getElementById('new-file').click()")
            wait("document.getElementById('file-label').textContent==='program.py'")
            inert='import json,sys\n# Literal untrusted text: <img src=x onerror=window.__xss=1>\nprint(json.dumps(json.load(sys.stdin)))\n'
            evaluate("document.getElementById('file-text').value="+json.dumps(inert)+";document.getElementById('save-file').click()")
            wait("document.getElementById('notice').textContent==='Saved the workspace copy.'")
            evaluate("document.getElementById('new-session').click()")
            wait("!document.getElementById('send').disabled")
            record['checks']['project_file_session_controls']=True
            record['checks']['untrusted_file_literal']=evaluate("document.getElementById('file-text').value.includes('<img')&&!window.__xss&&document.querySelectorAll('img').length===0")
            record['captures']['editable-copy-desktop.png']=screenshot('editable-copy-desktop.png')
            evaluate("document.getElementById('start-window').click()")
            wait("document.getElementById('details').open")
            record['checks']['start_requires_native_explicit_window']=evaluate("document.getElementById('details-text').textContent.includes('sudo')")
            record['captures']['explicit-window-command.png']=screenshot('explicit-window-command.png')
            evaluate("document.getElementById('details').close()")
            subprocess.run(['/usr/bin/systemctl','--user','restart','hermes-workspace.service'],check=True,timeout=10)
            wait("document.getElementById('connection').textContent.includes('connected')")
            time.sleep(2.5)
            wait("document.getElementById('connection').textContent.includes('connected')")
            evaluate("document.getElementById('new-session').click()")
            wait("!document.getElementById('send').disabled")
            record['checks']['reconnect_after_service_restart']=True
            for width,height,name in [(900,900,'workspace-tablet.png'),(390,844,'workspace-mobile.png'),(320,720,'workspace-320.png')]:
                metric(width,height);time.sleep(.3)
                record['checks']['no_horizontal_overflow_'+str(width)]=evaluate("document.documentElement.scrollWidth<=innerWidth")
                record['checks']['create_controls_visible_'+str(width)]=evaluate("['new-project','new-session'].every(id=>document.getElementById(id).getBoundingClientRect().height>0)")
                record['captures'][name]=screenshot(name)
            metric(390,844);evaluate("document.getElementById('files-toggle').click()")
            time.sleep(.2);record['captures']['mobile-file-review.png']=screenshot('mobile-file-review.png')
            evaluate("document.getElementById('files-toggle').click()")
            metric(1440,900)
            for _ in range(8):evaluate('document.title');time.sleep(.2)
            pipe.call('Page.stopScreencast',{},session);pipe.on_event=None
            if len(frames)<3:raise RuntimeError('real_browser_recording_missing')
            concat=Path(directory)/'frames.txt'
            rows=[]
            for index,(name,timestamp) in enumerate(frames):
                rows.append("file '"+str(name)+"'")
                if index+1<len(frames):rows.append('duration '+str(max(.02,min(4,frames[index+1][1]-timestamp))))
            rows.append("file '"+str(frames[-1][0])+"'");concat.write_text('\n'.join(rows)+'\n')
            video=evidence/'workspace-interaction.mp4'
            subprocess.run(['/usr/bin/ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,timeout=60)
            record['recording']={'kind':'actual_CDP_browser_screencast','frames':len(frames),'elapsed_seconds':frames[-1][1]-frames[0][1],'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'physical_input_or_motion_approval':False}
        record['all_passed']=all(record['checks'].values())
        (evidence/'ui-probe.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record));return 0 if record['all_passed'] else 2
    finally:
        try:pipe.call('Browser.close')
        except (OSError,RuntimeError,TimeoutError):pass
        os.close(pipe.read);os.close(pipe.write)


if __name__=='__main__':raise SystemExit(main())
