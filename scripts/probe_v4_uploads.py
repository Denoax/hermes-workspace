"""Upload a pinned public speech fixture and harmless UTF-8 through the real pin.

No physical microphone, Qwen inference, replacement response or isolated server.
The sample remains private; return only identities and transcript/metadata checks.
New attachment IDs are positively recorded for the parent's scoped cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc
from workspace import launcher

BASE = Path('/home/mani/mani-hermes-v4-d1wzr5kx')
REVISION = 'a8d002cfd879315632a579e73f0148d06959de36'
SAMPLE_SHA256 = '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e'
SAMPLE_BLOB = '3184d372cd2f8b804d3a540c70ec50d927b335d2'
OBSERVE_UPLOADS = r'''(() => {
 const original=globalThis.fetch;const records=[];let pending=0;
 const wrapped=function(...args){
  const value=args[0];const url=typeof value==='string'?value:value?.url;
  const watched=url && new URL(url,location.href).pathname==='/hermes-workspace/api/upload';
  const response=Reflect.apply(original,this,args);
  if(watched){pending++;response.then(r=>r.clone().json()).then(body=>{
   const r=body.result;if(r?.id)records.push({id:r.id,name:r.name,mime:r.mime,bytes:r.bytes,sha256:r.sha256});
  }).finally(()=>pending--).catch(()=>{});}
  return response;
 };
 globalThis.fetch=wrapped;
 globalThis.__hermesUploadReview={records,summary:()=>({records,pending}),cleanup:()=>{if(globalThis.fetch===wrapped)globalThis.fetch=original;}};
})()'''


class UploadGap(RuntimeError):
    pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--permission-record',type=Path,default=BASE/'review/permissions/permissions.json')
    parser.add_argument('--fixture',type=Path,default=BASE/'private-state/voice-fixture/public-jfk.wav')
    args=parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    if args.output.is_symlink() or args.output.stat().st_mode&0o077:
        raise ValueError('private_review_directory_required')
    if args.fixture.is_symlink() or args.fixture.stat().st_size>2*1024*1024:
        raise ValueError('bounded_real_public_sample_required')
    raw=args.fixture.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SAMPLE_SHA256 or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=SAMPLE_BLOB:
        raise ValueError('pinned_official_sample_identity_required')
    tracked=json.loads(args.permission_record.read_text());session=tracked.get('session_id');project=tracked.get('project_id')
    if not session or session not in tracked.get('sessions',[]) or not project:
        raise ValueError('positively_tracked_permission_test_conversation_required')
    report={'status':'IN_PROGRESS','scope':'actual existing Hermes pin/profile/catalog and authenticated port18791; official public speech sample, not physical microphone evidence',
            'session_id':session,'checks':{},'attachments_created':[], 'cleanup':{},
            'source':{'repository':'https://github.com/ggml-org/whisper.cpp','revision':REVISION,'path':'samples/jfk.wav','url':'https://github.com/ggml-org/whisper.cpp/blob/'+REVISION+'/samples/jfk.wav','git_blob_sha1':SAMPLE_BLOB,'sha256':SAMPLE_SHA256,'bytes':len(raw)},
            'privacy':{'physical_microphone_used':False,'Qwen_inference_started':False,'public_sample_audio_in_review_or_source':False,'original_draft_or_attachment_contents_exported':False},
            'remaining':['This fixture is not physical speech/microphone quality or a native file-picker test.','Only positively recorded new attachment IDs may be removed during final scoped cleanup.']}
    target=args.output/'uploads.json'
    def save():target.write_text(json.dumps(report,indent=2)+'\n');target.chmod(0o600)
    save();browser=None;previous_view=None;original_draft=None;observing=False;leave_open=False;temporary=None;upload_names=[]
    def evaluate(source):return browser.evaluate(source)
    def trusted_click(selector):
        evaluate('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center",inline:"nearest"})')
        browser.click(selector)
    def attachment_count():return evaluate('document.querySelectorAll("#composer .attachment").length')
    def detach_preserving_browser():
        browser.pipe.call('Target.detachFromTarget',{'sessionId':browser.session})
        for descriptor in (browser.pipe.read,browser.pipe.write):os.close(descriptor)
        browser.pipe=None
        if browser.paused:signal.pidfd_send_signal(browser.owner,signal.SIGCONT);browser.paused=False
        os.close(browser.owner);browser.owner=None
    try:
        browser=ProductionPin();report['pin']=browser.identity
        previous_view=rpc(browser,'view.read',{})
        # Unsent attachment objects belong to this live document. Do not reload
        # or close it to simplify a probe if such state is unexpectedly present.
        if attachment_count():
            leave_open=True
            raise UploadGap('preexisting_unsent_attachments_preserved_probe_not_started')
        selected={**previous_view,'project_id':project,'session_id':session,'arm':'normal'}
        if previous_view.get('session_id')!=session or previous_view.get('project_id')!=project:
            rpc(browser,'view.write',{'state':selected});browser.call('Page.reload')
            browser.wait('document.getElementById("connection")?.textContent==="Connected"')
        browser.wait('!!document.querySelector("#prompt")&&!document.querySelector("#prompt").disabled')
        if attachment_count():
            leave_open=True
            raise UploadGap('tracked_conversation_unsent_attachments_preserved_probe_not_started')
        original_draft=rpc(browser,'draft.read',{'session_id':session})
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if evaluate('document.querySelector("#prompt").value')==original_draft['text']:break
            time.sleep(.025)
        else:
            leave_open=True
            raise UploadGap('draft_loading_or_unsaved_input_preserved_probe_not_started')
        caps=rpc(browser,'capabilities.read',{})
        if not caps.get('attachments') or not caps.get('transcription'):
            raise UploadGap('local_CPU_transcription_or_attachment_support_unavailable')
        installed=json.loads((Path.home()/'.local/share/hermes-workspace/stt/installation.json').read_text())
        if installed.get('source_revision')!=REVISION or installed.get('CPU_only') is not True:
            raise UploadGap('pinned_CPU_transcription_provenance_not_current')
        report['CPU_transcription']={'source_revision':installed['source_revision'],'CPU_only':True,'files':installed['files']}
        evaluate(OBSERVE_UPLOADS);observing=True
        # This profile parent is intentionally visible to the actual Brave
        # Flatpak. The temporary directory contains public/harmless fixtures only.
        temporary=tempfile.TemporaryDirectory(prefix='hermes-v4-upload-',dir=launcher.PROFILE.parent)
        directory=Path(temporary.name);directory.chmod(0o700)
        nonce='utf8-'+uuid.uuid4().hex[:10]
        text=('Hermes v4 harmless UTF-8 attachment verification\n'+nonce+'\nUnicode: café, naïve, Ω.\n').encode()
        text_file=directory/(nonce+'.txt');text_file.write_bytes(text);text_file.chmod(0o600)
        speech_file=directory/'public-jfk.wav';speech_file.write_bytes(raw);speech_file.chmod(0o600)
        upload_names=[text_file.name,speech_file.name]
        document=browser.call('DOM.getDocument')['root']['nodeId']
        node=browser.call('DOM.querySelector',{'nodeId':document,'selector':'#composer input[type="file"]'})['nodeId']
        if not node:raise AssertionError('actual_composer_file_input_missing')
        started=time.monotonic()
        browser.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(text_file)]})
        browser.wait('document.querySelectorAll("#composer .attachment").length===1',timeout=15)
        browser.wait('globalThis.__hermesUploadReview.summary().records.length===1',timeout=10)
        first=evaluate('globalThis.__hermesUploadReview.summary().records[0]');report['attachments_created'].append(first['id']);save()
        metadata=rpc(browser,'attachment.metadata',{'id':first['id']})
        if metadata['sha256']!=hashlib.sha256(text).hexdigest() or metadata['bytes']!=len(text) or metadata['mime']!='text/plain':
            raise AssertionError('actual_UTF8_upload_metadata_mismatch')
        report['checks']['actual_UTF8_upload']={'id':metadata['id'],'sha256':metadata['sha256'],'bytes':metadata['bytes'],'mime':metadata['mime'],'observed_total_seconds':time.monotonic()-started}
        started=time.monotonic()
        browser.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(speech_file)]})
        browser.wait('globalThis.__hermesUploadReview.summary().records.length===2',timeout=20)
        second=evaluate('globalThis.__hermesUploadReview.summary().records[1]');report['attachments_created'].append(second['id']);save()
        browser.wait('document.querySelectorAll("#composer .attachment").length===2',timeout=150)
        metadata=rpc(browser,'attachment.metadata',{'id':second['id']});voice=metadata['metadata'];transcript=voice.get('transcript','')
        normalized=' '.join(transcript.lower().split())
        if metadata['sha256']!=SAMPLE_SHA256 or metadata['bytes']!=len(raw) or metadata['mime']!='audio/wav':raise AssertionError('public_speech_upload_identity_mismatch')
        waveform=voice.get('waveform',[]);duration=voice.get('duration',0)
        if 'ask not' not in normalized or voice.get('method')!='local_whisper_cpp_CPU' or not 10.9<=duration<=11.1 or len(waveform)!=40 or not all(type(x)in(int,float)and 0<=x<=1 for x in waveform) or not any(x>0 for x in waveform):
            raise AssertionError('actual_CPU_transcription_or_waveform_contract_failed')
        draft=evaluate('document.querySelector("#prompt").value')
        if 'ask not' not in ' '.join(draft.lower().split()) or (original_draft['text'] and not draft.startswith(original_draft['text'])):
            raise AssertionError('actual_transcript_not_appended_to_preserved_draft')
        report['checks']['actual_public_speech_CPU_transcription']={'id':metadata['id'],'sha256':metadata['sha256'],'bytes':metadata['bytes'],'mime':metadata['mime'],'duration_seconds':duration,'waveform_bars':len(waveform),'waveform_peak':max(waveform),'method':voice['method'],'transcript_contains_ask_not':True,'transcript_sha256':hashlib.sha256(transcript.encode()).hexdigest(),'transcript_characters':len(transcript),'observed_total_seconds':time.monotonic()-started}
        report['checks']['actual_UI_attachment_cards_and_transcript_draft']=True
        report['status']='PASS'
    except UploadGap as error:report.update(status='PARTIAL',gap=str(error))
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__,error_detail=str(error)[:600])
    finally:
        if browser is not None:
            if observing:
                try:
                    records=evaluate('globalThis.__hermesUploadReview.summary().records')
                    report['attachments_created']=list(dict.fromkeys([*report['attachments_created'],*[r['id']for r in records if r['name']in upload_names]]))
                    for name in upload_names:
                        selector='#composer button[aria-label='+json.dumps('Remove '+name)+']'
                        if evaluate('!!document.querySelector('+json.dumps(selector)+')'):trusted_click(selector)
                    evaluate('globalThis.__hermesUploadReview.cleanup()')
                    report['cleanup']['only_probe_unsent_attachments_removed']=attachment_count()==0
                except Exception as error:report['cleanup']['attachment_error']=type(error).__name__;report['status']='FAIL'
            if original_draft is not None:
                try:
                    trusted_click('#prompt');browser.key('a',modifiers=2);browser.key('Backspace')
                    if original_draft['text']:browser.call('Input.insertText',{'text':original_draft['text']})
                    time.sleep(.5)
                    rpc(browser,'draft.write',{'session_id':session,'text':original_draft['text'],'mode':original_draft.get('mode','chat')})
                    restored=rpc(browser,'draft.read',{'session_id':session})
                    report['cleanup']['original_draft_restored']=restored['text']==original_draft['text']
                except Exception as error:report['cleanup']['draft_error']=type(error).__name__;report['status']='FAIL'
            if previous_view is not None and not leave_open:
                try:rpc(browser,'view.write',{'state':previous_view});browser.call('Page.reload');report['cleanup']['previous_view_restored']=True
                except Exception as error:report['cleanup']['view_error']=type(error).__name__;report['status']='FAIL'
            try:
                if leave_open:detach_preserving_browser();report['cleanup']['pin_left_open_to_preserve_unsent_attachments']=True
                else:browser.close();report['cleanup']['production_browser_closed']=True
            except Exception as error:report['cleanup']['browser_error']=type(error).__name__;report['status']='FAIL'
        if temporary is not None:temporary.cleanup();report['cleanup']['temporary_public_fixture_copies_removed']=True
        report['cleanup']['new_server_attachment_IDs_recorded_for_scoped_cleanup']=True
        save()
    print(json.dumps({'status':report['status'],'new_attachment_count':len(report['attachments_created']),'physical_microphone_used':False,'Qwen_inference_started':False}))
    if report['status']=='FAIL':raise SystemExit(2)


if __name__=='__main__':main()
