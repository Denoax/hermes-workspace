"""Actual normal-Qwen attachment/search/cancel/reload acceptance via rendered UI."""
import argparse,json,shutil,sys,tempfile,time,uuid,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace import launcher
from workspace.parity_browser import Browser
from scripts.probe_chat_features import prepare
from scripts.probe_chat_live import rpc
from workspace.capture import Recording


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--voice-fixture',type=Path,required=True);p.add_argument('--record',action='store_true');args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True,mode=0o700)
    launcher.ORIGIN='http://127.0.0.1:18793';b=Browser('local-chat-flow',fixture=False,quiet=True);prepare(b);report={'kind':'actual local normal Qwen and real Wikipedia; harmless file/speech fixtures','checks':{},'status':'IN_PROGRESS'}
    checks=report['checks'];nonce='ORCHID-'+uuid.uuid4().hex[:8];recording=None
    def type_text(text):b.click('#prompt');b.key('a','KeyA',2);b.call('Input.insertText',{'text':text})
    def wait_run(sid,expected,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            snap=rpc(b,'chat.snapshot',{'session_id':sid});r=snap['runs'][-1] if snap['runs'] else None
            if r and r['state'] in ('completed','cancelled','failed'):
                if r['state']!=expected:raise RuntimeError('actual_run_'+r['state']+':'+str(r.get('error')))
                return snap
            time.sleep(.7)
        raise TimeoutError('actual_flow_deadline')
    try:
        sid=rpc(b,'session.create',{'project_id':None,'arm':'normal'})['id']
        rpc(b,'view.write',{'state':{'project_id':None,'session_id':sid,'file_path':None,'editor':None,'files_open':False,'arm':'normal','task_kind':'chat','theme':'dark','motion':'system'}})
        b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'");prepare(b);b.metric(1440,900);time.sleep(.7)
        if args.record:
            recording=Recording(b,out/'unedited-motion.mp4')
            b.click('[aria-label="Reasoning effort"]');recording.hold(.8);b.key('Escape');b.click('#plus-menu');recording.hold(.7);b.key('Escape')
            for _ in range(2):b.click('#files-toggle');recording.hold(.12);b.click('#settings-toggle');recording.hold(.15);b.key('Escape');recording.hold(.12)
            b.click('#theme-buddy');recording.hold(.6);b.click('#theme-buddy');recording.hold(.6)
        with tempfile.TemporaryDirectory(prefix='hermes-voice-flow-',dir=launcher.PROFILE.parent) as directory:
            text=Path(directory)/'verification.txt';text.write_text('The launch code is '+nonce+'. This is an inert acceptance fixture.\n')
            speech=Path(directory)/'public-speech-fixture.wav';shutil.copy2(args.voice_fixture,speech)
            doc=b.call('DOM.getDocument')['root']['nodeId'];node=b.call('DOM.querySelector',{'nodeId':doc,'selector':'input[type=file]'})['nodeId']
            b.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(text),str(speech)]})
            b.wait("document.querySelectorAll('.attachment').length===2 || document.querySelectorAll('[aria-label=\"Play voice message\"]').length===1",timeout=60)
            b.wait("document.querySelector('#prompt').value.toLowerCase().includes('ask not')",timeout=60)
            if recording:
                b.click('[aria-label="Play voice message"]');recording.hold(1);b.click('[aria-label^="Playback speed"]');b.click('[aria-label="Seek"]');recording.hold(.8);b.click('[aria-label="Pause voice message"]')
        b.click('#plus-menu');b.dialog_click('[role=menu] button:last-child','Llama language model')
        b.wait("!!document.querySelector('.search-intent')")
        type_text('Read my attached verification file and speech transcript. State the launch code exactly and quote the words "ask not what your country" from the speech. Then use the Wikipedia results to give one short fact about Llama and cite a full source URL. Keep the answer short.')
        started=time.monotonic();b.key('Enter');b.key('Enter');snap=wait_run(sid,'completed');report['search_and_attachment_seconds']=time.monotonic()-started
        answer=''.join(m['text'] for m in snap['messages'] if m['role']=='assistant');report['answer']=answer;report['run']=snap['runs'][-1]
        links=b.evaluate("[...document.querySelectorAll('.message.assistant a')].map(a=>a.href)")
        actual_urls={s['url'] for e in snap['activity'] if e['type']=='search' for s in e['sources']}
        report['model_full_url_request_obeyed']='wikipedia.org/wiki/' in answer
        report['resolved_citation_urls']=links
        checks['real_attachment_content']=nonce in answer;checks['speech_context']='ask not what your country' in answer.lower();checks['real_search_sources']=bool(actual_urls);checks['sourced_answer']=bool(actual_urls.intersection(links));checks['repeated_enter_one_run']=len(snap['runs'])==1
        b.capture(out/'sourced-answer.png')
        if recording:
            b.click('.run-tasks summary');recording.hold(.8)
        type_text('Write a very long numbered list of at least 300 interesting facts. Do not stop early.');b.click('#send')
        b.wait("!!document.querySelector('#cancel-response')");b.wait("document.querySelectorAll('.message.assistant').length===2",timeout=60)
        before=rpc(b,'chat.snapshot',{'session_id':sid});run_id=before['runs'][-1]['id']
        b.call('Page.reload');b.wait("document.getElementById('connection')?.textContent==='Connected'");prepare(b);b.wait("!!document.querySelector('#cancel-response')")
        checks['reload_same_active_run']=rpc(b,'chat.snapshot',{'session_id':sid})['runs'][-1]['id']==run_id
        stopped=time.monotonic();b.click('#cancel-response');cancelled=wait_run(sid,'cancelled',30);report['cancel_seconds']=time.monotonic()-stopped
        with urllib.request.urlopen('http://127.0.0.1:8080/slots',timeout=3) as response:slots=json.load(response)
        checks['actual_compute_idle']=all(s['is_processing'] is False for s in slots);checks['partial_answer_retained']=any(m['role']=='assistant' and m.get('job')==run_id and m['text'] for m in cancelled['messages']);checks['no_duplicate_after_reconnect']=len(cancelled['runs'])==2
        b.wait("!document.querySelector('#cancel-response')");b.capture(out/'cancelled-reloaded.png')
        checks['UI_matches_durable_history']=b.evaluate("[...document.querySelectorAll('.message.assistant .message-text')].map(e=>e.textContent)")[-1].strip()!=''
        if recording:
            b.click('.session-options');b.click('[aria-label="Delete"]');recording.hold(.7);b.click('[aria-label="Cancel"]');recording.hold(.6)
            b.click('[aria-label="Delete"]');recording.hold(.5);b.click('[aria-label="Confirm delete"]');recording.hold(1);b.key('Escape');recording.hold(.6)
        report['status']='PASS' if all(checks.values()) else 'FAIL'
    except Exception as error:
        report.update(status='FAIL',error=str(error))
        try:b.capture(out/'failure.png')
        except (OSError,RuntimeError,TimeoutError):pass
        raise
    finally:
        if recording:report['recording']=recording.finish()
        (out/'flow.json').write_text(json.dumps(report,indent=2)+'\n');b.close()
    print(json.dumps({'status':report['status'],'checks':checks,'cancel_seconds':report.get('cancel_seconds')}))

if __name__=='__main__':main()
