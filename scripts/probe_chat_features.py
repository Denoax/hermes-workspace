"""Actual renderer/CRUD/media checks in the separate acceptance catalog.

Speech is an explicitly labelled public fixture; this is not a microphone test.
Use serve_chat_acceptance.py. No production catalog changes or fake responses.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workspace import launcher
from workspace.parity_browser import Browser
from scripts.probe_chat_live import rpc


def prepare(browser):
    browser.evaluate("(async()=>{const b=await(await fetch('/hermes-workspace/api/bootstrap')).json();window.__liveRpc=async(method,fields)=>{const r=await fetch('/hermes-workspace/api/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':b.csrf},body:JSON.stringify({version:1,method,fields})});const d=await r.json();if(d.error)throw Error(d.error);return d.result;};})()")


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--voice-fixture',type=Path,required=True);parser.add_argument('--port',type=int,choices=(18793,18794),default=18794);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    launcher.ORIGIN='http://127.0.0.1:'+str(args.port);b=Browser('local-chat-features',fixture=False,quiet=True);prepare(b)
    result={'kind':'actual authenticated UI/API; isolated catalog; public speech fixture, not physical microphone','checks':{},'status':'IN_PROGRESS'}
    fixture_directory=tempfile.TemporaryDirectory(prefix='hermes-public-speech-fixture-',dir=launcher.PROFILE.parent)
    speech=Path(fixture_directory.name)/'public-speech-fixture.wav';shutil.copy2(args.voice_fixture,speech)
    checks=result['checks'];created=[]
    def reload():
        b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'");prepare(b);time.sleep(.6)
    def type_text(text):
        b.click('#prompt');b.key('a','KeyA',2);b.call('Input.insertText',{'text':text})
    def upload(path):
        document=b.call('DOM.getDocument')['root']['nodeId'];node=b.call('DOM.querySelector',{'nodeId':document,'selector':'input[type=file]'})['nodeId']
        b.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(path.resolve())]})
    try:
        b.metric(1440,900);b.click('#new-session');time.sleep(.6)
        type_text('Keyboard fixture');b.key('Enter',modifiers=8)
        checks['shift_enter_inserts_line']=b.evaluate("document.querySelector('#prompt').value.endsWith('\\n')")
        type_text(('A real long draft\n')*40);time.sleep(.1)
        result['grown_textarea']=b.evaluate("(()=>{const e=document.querySelector('#prompt');return {height:e.clientHeight,scroll:e.scrollHeight}})()")
        checks['bounded_growth']=result['grown_textarea']['height']<=160 and result['grown_textarea']['scroll']>160
        type_text('Draft survives a real reload');time.sleep(.65);reload()
        checks['draft_reload']=b.evaluate("document.querySelector('#prompt').value==='Draft survives a real reload'")
        parent=rpc(b,'workspace.create',{'label':'Acceptance project'});created.append(parent['id'])
        child=rpc(b,'workspace.create',{'label':'Acceptance child'});created.append(child['id'])
        rpc(b,'folder.update',{'project_id':child['id'],'label':'Renamed child','parent':parent['id'],'color':'orange'})
        reload();folders=rpc(b,'workspace.list',{});row=next(f for f in folders if f['id']==child['id'])
        checks['folder_parent_name_colour_reload']=row['parent']==parent['id'] and row['color']=='orange' and row['label']=='Renamed child'
        b.click('#new-session');type_text('')
        for _ in range(2):
            upload(speech);b.wait("document.querySelectorAll('[aria-label=\"Play voice message\"]').length>="+str(_+1),timeout=60)
        checks['local_voice_transcript_visible']=b.evaluate("document.querySelector('#prompt').value.toLowerCase().includes('ask not what your country can do for you')")
        b.click('[aria-label="Play voice message"]');b.wait("[...document.querySelectorAll('audio')].some(a=>!a.paused&&a.currentTime>0)")
        b.click('[aria-label^="Playback speed"]');checks['playback_speed']=b.evaluate("[...document.querySelectorAll('audio')].some(a=>a.playbackRate===1.5)")
        b.click('[aria-label="Seek"]');checks['seek_uses_audio_clock']=b.evaluate("[...document.querySelectorAll('audio')].some(a=>a.currentTime>2)")
        b.click('[aria-label="Play voice message"]');time.sleep(.2)
        checks['one_player']=b.evaluate("[...document.querySelectorAll('audio')].filter(a=>!a.paused).length===1")
        b.capture(args.output/'voice-fixture.png')
        b.evaluate("document.querySelectorAll('audio').forEach(a=>a.pause())")
        # Real UI deletion: Escape/cancel retain records; success follows RPC.
        b.click('[aria-label="Edit Acceptance project"]');b.wait("!!document.querySelector('dialog[open]')")
        b.click('[aria-label="Delete"]');b.wait("!!document.querySelector('[aria-label=\"Confirm delete\"]')");b.key('Escape')
        checks['delete_escape_retains']=any(f['id']==parent['id'] for f in rpc(b,'workspace.list',{}))
        # Escape closes the host panel as well as cancelling its confirmation.
        if not b.evaluate("!!document.querySelector('dialog[open]')"):b.click('[aria-label="Edit Acceptance project"]')
        b.click('[aria-label="Delete"]');b.wait("!!document.querySelector('[aria-label=\"Cancel\"]')");b.click('[aria-label="Cancel"]');time.sleep(.4)
        checks['delete_cancel_retains']=any(f['id']==parent['id'] for f in rpc(b,'workspace.list',{}))
        b.click('[aria-label="Delete"]');b.wait("!!document.querySelector('[aria-label=\"Confirm delete\"]')");b.click('[aria-label="Confirm delete"]')
        end=time.monotonic()+6
        while time.monotonic()<end:
            if not any(f['id']==parent['id'] for f in rpc(b,'workspace.list',{})):break
            time.sleep(.7)
        checks['confirmed_subtree_delete']=not any(f['id'] in created for f in rpc(b,'workspace.list',{}))
        b.key('Escape');b.capture(args.output/'empty-after-test-delete.png')
        result['status']='PASS' if all(checks.values()) else 'FAIL'
    except Exception as error:
        result['status']='FAIL';result['error']=str(error);b.capture(args.output/'feature-failure.png');raise
    finally:
        (args.output/'features.json').write_text(json.dumps(result,indent=2)+'\n');b.close();fixture_directory.cleanup()
    print(json.dumps(result))


if __name__=='__main__':main()
