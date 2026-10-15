"""Click the actual authenticated UI Stop control for one registered live job."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace import launcher
from lab.workspace_contract import canonical_id


def main():
    parser=argparse.ArgumentParser();parser.add_argument('project');parser.add_argument('session');parser.add_argument('job');args=parser.parse_args()
    for value in (args.project,args.session,args.job):canonical_id(value)
    if os.geteuid()==0:raise SystemExit('normal-user browser test only')
    launcher.PROFILE=launcher.PROFILE.parent/'hermes-workspace-live-probe'
    pipe,process=launcher.browser(headless=True)
    try:
        target=next(x for x in pipe.call('Target.getTargets')['targetInfos'] if x.get('type')=='page' and x.get('url','').startswith(launcher.ORIGIN))
        session=pipe.call('Target.attachToTarget',{'targetId':target['targetId'],'flatten':True})['sessionId']
        pipe.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False},session)
        def evaluate(code):return pipe.call('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True},session).get('result',{}).get('value')
        def wait(code):
            deadline=time.monotonic()+18
            while time.monotonic()<deadline:
                if evaluate(code):return
                time.sleep(.15)
            raise RuntimeError('live_UI_Stop_state_deadline')
        wait("document.getElementById('connection').textContent.includes('connected')")
        selector='button[data-id="'+args.project+'"]'
        evaluate('document.querySelector('+json.dumps(selector)+').click()')
        selector='button[data-id="'+args.session+'"]'
        wait('!!document.querySelector('+json.dumps(selector)+')')
        evaluate('document.querySelector('+json.dumps(selector)+').click()')
        wait("!document.getElementById('stop').disabled")
        evidence=ROOT/'workspace/evidence'
        (evidence/'actual-live-stop-before.png').write_bytes(base64.b64decode(pipe.call('Page.captureScreenshot',{'format':'png'},session)['data']))
        evaluate("document.getElementById('stop').click()")
        wait("document.getElementById('stop').disabled")
        (evidence/'actual-live-stop-after.png').write_bytes(base64.b64decode(pipe.call('Page.captureScreenshot',{'format':'png'},session)['data']))
        print(json.dumps({'actual_browser_Stop_clicked':True,'job_id':args.job,'evidence_kind':'native_authenticated_UI_control'}))
    finally:
        try:pipe.call('Browser.close')
        except (OSError,RuntimeError,TimeoutError):pass
        os.close(pipe.read);os.close(pipe.write)


if __name__=='__main__':main()
