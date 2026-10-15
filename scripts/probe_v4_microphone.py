"""Bounded real-device microphone review through the existing production pin.

No fake device, replacement media stream, audio export, transcription or model
request is used. Only the positively tracked permissions-test conversation is
changed. Browser microphone permission, its server policy and view are restored.
Run only when the production pin is free of other acceptance/native work.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc

ORIGIN = 'http://127.0.0.1:18791'
DEFAULT_RECORD = Path('/home/mani/mani-hermes-v4-d1wzr5kx/review/permissions/permissions.json')

# This delegates every request to the real browser implementation and returns the
# same MediaStream. Only scalar counters/RMS values leave the page. Independent
# timers bound total live-device time even if the reviewer/CDP pipe is delayed.
INSTRUMENT = r'''(() => {
  if (globalThis.__hermesMicReview) throw Error('microphone_review_already_installed');
  const devices = navigator.mediaDevices;
  if (!devices?.getUserMedia) throw Error('real_microphone_API_unavailable');
  const original = devices.getUserMedia;
  const streams = [];
  const errors = [];
  let requests = 0, successes = 0, retired = false, usedMs = 0;
  const budgetMs = 1800;
  const summary = () => ({requests, successes, error_names: [...errors],
    streams: streams.length,
    live_audio_tracks: streams.reduce((n,s) => n+s.tracks.filter(t=>t.readyState==='live').length,0),
    ended_audio_tracks: streams.reduce((n,s) => n+s.tracks.filter(t=>t.readyState==='ended').length,0),
    capture_ms: streams.reduce((n,s) => n+(s.endedMs ?? performance.now()-s.started),0),
    max_rms: Math.max(0,...streams.map(s=>s.maxRms)),
    rms_samples: streams.reduce((n,s)=>n+s.samples,0),
    audio_contexts_open: streams.filter(s=>s.context && s.context.state!=='closed').length,
    safety_budget_triggered: streams.some(s=>s.safetyTriggered),
    aggregate_capture_budget_ms: budgetMs,
    real_getUserMedia_delegated: true,
    audio_exported: false, device_labels_collected: false});
  const finish = entry => {
    if (entry.endedMs !== null || entry.tracks.some(t=>t.readyState==='live')) return;
    entry.endedMs = performance.now()-entry.started;
    usedMs += entry.endedMs;
    clearTimeout(entry.timer);clearInterval(entry.meterTimer);
    try { entry.source?.disconnect(); } catch {}
    if (entry.context && entry.context.state!=='closed') entry.closing=entry.context.close().catch(error=>errors.push(error?.name ?? 'ContextCloseError'));
  };
  const stop = entry => {
    entry.tracks.forEach(track=>{if(track.readyState==='live') track.stop();});finish(entry);
  };
  const wrapped = async function(...args) {
    requests++;
    let stream;
    try { stream = await Reflect.apply(original, devices, args); }
    catch (error) { errors.push(error?.name ?? 'UnknownError');throw error; }
    const tracks = stream.getAudioTracks();
    const entry = {tracks,started:performance.now(),endedMs:null,maxRms:0,samples:0,
      context:null,source:null,timer:0,meterTimer:0,closing:null,safetyTriggered:false};
    streams.push(entry);successes++;
    for (const track of tracks) {
      const nativeStop = track.stop.bind(track);
      track.stop = () => {nativeStop();finish(entry);};
      track.addEventListener('ended',()=>finish(entry),{once:true});
    }
    const remaining = budgetMs-usedMs;
    if (retired || remaining<=0) {stop(entry);throw new DOMException('Review capture budget ended','AbortError');}
    entry.timer=setTimeout(()=>{entry.safetyTriggered=true;stop(entry);},remaining);
    try {
      const context = new AudioContext();entry.context=context;
      const source=context.createMediaStreamSource(stream);entry.source=source;
      const analyser=context.createAnalyser();analyser.fftSize=512;source.connect(analyser);
      const data=new Float32Array(analyser.fftSize);
      void context.resume().catch(()=>{});
      entry.meterTimer=setInterval(()=>{
        if(entry.endedMs!==null)return;
        analyser.getFloatTimeDomainData(data);
        let sum=0;for(const value of data)sum+=value*value;
        entry.maxRms=Math.max(entry.maxRms,Math.sqrt(sum/data.length));entry.samples++;
      },50);
    } catch (error) {errors.push(error?.name ?? 'MeterUnavailable');}
    return stream;
  };
  devices.getUserMedia=wrapped;
  globalThis.__hermesMicReview={summary,cleanup:async()=>{
    retired=true;streams.forEach(stop);
    if(devices.getUserMedia===wrapped)devices.getUserMedia=original;
    await Promise.all(streams.map(s=>s.closing));
    return summary();
  }};
  return summary();
})()'''


class ProbeGap(RuntimeError):
    """An unavailable real browser/device check, never a fabricated pass."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--permission-record', type=Path, default=DEFAULT_RECORD)
    parser.add_argument('--playback-only',action='store_true',help='One final <=500ms stream; preserve prior cancellation proof and cumulative <=1800ms budget.')
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.is_symlink() or args.output.stat().st_mode & 0o077:
        raise ValueError('private_review_directory_required')
    tracked = json.loads(args.permission_record.read_text())
    session = tracked.get('session_id')
    project = tracked.get('project_id')
    if not session or session not in tracked.get('sessions', []) or not project:
        raise ValueError('positively_tracked_permission_test_conversation_required')
    report = {'status':'IN_PROGRESS', 'scope':'actual Hermes pin/profile/catalog and authenticated port18791; real browser media API, no fake device',
              'session_id':session, 'checks':{}, 'cleanup':{},
              'privacy':{'raw_audio_exported':False,'raw_audio_uploaded':False,'device_labels_or_ids_collected':False,
                         'aggregate_capture_budget_ms':1800,'playback_muted':True},
              'unverified':['Physical listening quality, physical microphone speech intelligibility and human approval.',
                            'Native browser permission prompt clicking: origin-scoped CDP denial/grant is used.',
                            'Physical device unplug and device-loss recovery: source lifecycle regressions cover this separately.']}
    target = args.output / 'microphone.json'
    prior_capture_ms = 0.0
    if target.exists():
        prior = json.loads(target.read_text())
        prior_capture_ms = float(prior.get('cumulative_capture_ms', prior.get('cleanup',{}).get('device',{}).get('capture_ms',0)))
        history=args.output/'history';history.mkdir(mode=0o700,exist_ok=True)
        name='attempt-'+str(time.time_ns())+'.json'
        (history/name).write_bytes(target.read_bytes());(history/name).chmod(0o600)
        report['prior_attempt_evidence']='history/'+name
        report['prior_attempt_capture_ms']=prior_capture_ms
    report['phase']='startup'
    if args.playback_only:
        if prior_capture_ms>=1300:raise SystemExit('preserve_cumulative_capture_budget_no_more_device_tests')
        report['privacy']['aggregate_capture_budget_ms']=450
        report['privacy']['cumulative_capture_limit_ms']=1800
        report['final_device_attempt']=True
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n')
        target.chmod(0o600)
    save()
    browser = None
    previous_view = previous_policy = original_browser_permission = None
    policy_changed = False
    permission_overridden = False
    instrumented = False
    previous_event = None
    uploads = []

    def evaluate(expression):
        return browser.evaluate(expression)

    def click(selector):
        evaluate('(()=>{const e=document.querySelector('+json.dumps(selector)+');if(!e)throw Error("microphone_control_missing");e.scrollIntoView({block:"center",inline:"nearest"})})()')
        browser.click(selector)

    def button(label, dialog=None):
        key = 'microphone-' + uuid.uuid4().hex
        scope = 'document' if dialog is None else 'document.querySelector('+json.dumps(dialog)+')'
        evaluate('(()=>{const scope='+scope+';const e=[...scope.querySelectorAll("button")].find(e=>e.textContent.trim()==='+json.dumps(label)+');if(!e)throw Error("microphone_button_missing");e.dataset.micReview='+json.dumps(key)+';e.scrollIntoView({block:"center"})})()')
        browser.click('[data-mic-review="'+key+'"]')

    def no_open_dialogs():
        browser.wait('!document.querySelector(\'dialog[open]:not([aria-hidden="true"])\')', timeout=5)

    def close_dialog(label):
        selector='dialog[open][aria-label='+json.dumps(label)+'] [aria-label='+json.dumps('Close '+label)+']'
        if evaluate('!!document.querySelector('+json.dumps(selector)+')'):
            click(selector)
        browser.wait('!document.querySelector(\'dialog[open][aria-label='+json.dumps(label)+']:not([aria-hidden="true"])\')', timeout=5)

    def microphone_checkbox():
        key='microphone-policy'
        evaluate('(()=>{const labels=[...document.querySelectorAll(\'dialog[aria-label="Settings"] label.permission-setting\')];const e=labels.find(e=>e.querySelector("span")?.firstChild?.textContent.trim()==="Record microphone")?.querySelector("input");if(!e)throw Error("microphone_policy_checkbox_missing");e.dataset.micReview='+json.dumps(key)+';e.scrollIntoView({block:"center"})})()')
        return '[data-mic-review="'+key+'"]'

    def set_app_consent(value):
        nonlocal policy_changed
        if not evaluate('!!document.querySelector(\'dialog[open][aria-label="Settings"]:not([aria-hidden="true"])\')'):
            click('#settings-toggle')
            browser.wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]:not([aria-hidden="true"])\')')
        selector=microphone_checkbox()
        browser.wait('!document.querySelector('+json.dumps(selector)+').disabled')
        if evaluate('document.querySelector('+json.dumps(selector)+').checked') != value:
            click(selector);policy_changed=True
        browser.wait('document.querySelector('+json.dumps(selector)+').checked==='+str(value).lower()+'&&!document.querySelector('+json.dumps(selector)+').disabled')
        policy=rpc(browser,'permissions.read',{'session_id':session})
        if bool(policy['capabilities']['microphone']) != value:
            raise AssertionError('server_microphone_policy_did_not_match_UI')
        close_dialog('Settings')
        return {'server_consent':value,'policy_version':policy['version']}

    def set_browser_permission(value):
        nonlocal permission_overridden
        browser.pipe.call('Browser.setPermission', {'permission':{'name':'microphone'},'setting':value,'origin':ORIGIN,'embeddedOrigin':ORIGIN})
        permission_overridden=True
        state=evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)')
        if state != value:
            raise ProbeGap('browser_microphone_override_not_observable')
        return state

    def stats():
        return evaluate('globalThis.__hermesMicReview.summary()')

    def begin_real_capture():
        before=stats()['requests']
        click('[aria-label="Record voice note"]')
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            current=stats()
            if current['requests']>before and current['live_audio_tracks'] and evaluate('!!document.querySelector(\'dialog[open][aria-label="Recording"]:not([aria-hidden="true"])\')'):
                return current
            if current['requests']>before and len(current['error_names'])>1:
                raise ProbeGap('real_device_capture_unavailable:'+current['error_names'][-1])
            time.sleep(.025)
        raise ProbeGap('real_device_capture_did_not_start_before_deadline')

    try:
        browser=ProductionPin()
        report['pin']=browser.identity
        previous_event=browser.pipe.on_event
        def network_event(message):
            if message.get('method')=='Network.requestWillBeSent':
                url=message.get('params',{}).get('request',{}).get('url','')
                if url.split('?',1)[0]==ORIGIN+'/hermes-workspace/api/upload':uploads.append(True)
            if previous_event:previous_event(message)
        browser.pipe.on_event=network_event
        browser.call('Network.enable',{'maxPostDataSize':0,'maxTotalBufferSize':32768,'maxResourceBufferSize':8192})
        previous_view=rpc(browser,'view.read',{})
        selected={**previous_view,'session_id':session,'project_id':project,'arm':'normal'}
        rpc(browser,'view.write',{'state':selected})
        browser.call('Page.reload')
        browser.wait('document.getElementById("connection")?.textContent==="Connected"')
        browser.wait('!!document.querySelector("#permissions-mode")&&!document.querySelector("#permissions-mode").disabled')
        previous_policy=rpc(browser,'permissions.read',{'session_id':session})
        if previous_policy.get('grants'):
            raise ProbeGap('tracked_test_session_has_active_grants_preserved')
        original_browser_permission=evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)')
        if original_browser_permission not in ('prompt','granted','denied'):
            raise ProbeGap('original_browser_microphone_permission_unavailable')
        report['browser_permission_before']=original_browser_permission
        evaluate(INSTRUMENT.replace('const budgetMs = 1800;', 'const budgetMs = 450;') if args.playback_only else INSTRUMENT);instrumented=True
        # The actual Settings checkbox must reach the server before media APIs.
        report['phase']='server_app_denial'
        report['checks']['app_consent_off']=set_app_consent(False)
        calls_before=stats()['requests']
        click('[aria-label="Record voice note"]')
        browser.wait('!!document.querySelector(".error-banner")&&!!document.querySelector(\'dialog[open][aria-label="Settings"]\')')
        denied=stats()
        if denied['requests'] != calls_before or denied['live_audio_tracks']:
            raise AssertionError('app_denial_did_not_precede_browser_request')
        report['checks']['server_denial_before_getUserMedia']=True
        report['checks']['app_consent_on']=set_app_consent(True)
        report['phase']='browser_denial'
        report['checks']['browser_deny_setting']=set_browser_permission('denied')
        calls_before=stats()['requests']
        click('[aria-label="Record voice note"]')
        browser.wait('globalThis.__hermesMicReview.summary().requests>'+str(calls_before)+'&&globalThis.__hermesMicReview.summary().error_names.includes("NotAllowedError")')
        if stats()['live_audio_tracks']:
            raise AssertionError('denied_browser_started_audio_track')
        report['checks']['real_browser_denial_observed']=True
        report['phase']='real_record_cancel'
        report['checks']['browser_grant_setting']=set_browser_permission('granted')
        if not args.playback_only:
            begin_real_capture()
            time.sleep(.22)
            button('Cancel','dialog[open][aria-label="Recording"]')
            browser.wait('globalThis.__hermesMicReview.summary().live_audio_tracks===0')
            no_open_dialogs()
            cancelled=stats()
            report['checks']['real_record_cancel']={'all_audio_tracks_ended':True,'capture_ms':round(cancelled['capture_ms'],3),'rms_samples':cancelled['rms_samples']}
        else:
            report['checks']['cancel_scope']='Verified in retained prior attempts; not repeated in this final device attempt.'
        report['phase']='real_record_stop'
        begin_real_capture()
        time.sleep(.32)
        button('Stop recording','dialog[open][aria-label="Recording"]')
        browser.wait('globalThis.__hermesMicReview.summary().live_audio_tracks===0')
        browser.wait('!!document.querySelector(\'dialog[open][aria-label="Voice note"] audio\')',timeout=8)
        browser.wait('(()=>{const a=document.querySelector(\'dialog[open][aria-label="Voice note"] audio\');const c=document.querySelector(\'dialog[open][aria-label="Voice note"] [aria-label="Play voice message"]\');return a&&a.readyState>=1&&c&&!c.disabled})()',timeout=8)
        # The real app decoded this blob to create VoiceNote. Do not fetch a
        # blob through connect-src or invent a finite HTML audio duration:
        # MediaRecorder WebM may legitimately report Infinity there.
        metadata=evaluate('''(()=>{const a=document.querySelector('dialog[open][aria-label="Voice note"] audio');
          a.muted=true;a.volume=0;return {native_duration_finite:Number.isFinite(a.duration),
          native_duration_seconds:Number.isFinite(a.duration)?a.duration:null,
          real_decoded_VoiceNote_control_enabled:!document.querySelector('dialog[open][aria-label="Voice note"] [aria-label="Play voice message"]').disabled};})()''')
        report['checks']['actual_recorded_blob_metadata']=metadata
        report['phase']='muted_playback'
        click('dialog[open][aria-label="Voice note"] [aria-label="Play voice message"]')
        browser.wait('document.querySelector(\'dialog[open][aria-label="Voice note"] audio\').currentTime>0',timeout=5)
        playback=evaluate('(()=>{const a=document.querySelector(\'dialog[open][aria-label="Voice note"] audio\');return {native_duration_seconds:Number.isFinite(a.duration)?a.duration:null,current_time:a.currentTime,muted:a.muted,volume:a.volume}})()')
        click('dialog[open][aria-label="Voice note"] [aria-label="Pause voice message"]')
        browser.wait('document.querySelector(\'dialog[open][aria-label="Voice note"] audio\').paused')
        playback['paused_by_actual_control']=True
        report['checks']['real_record_stop_and_muted_playback']=playback
        button('Delete recording','dialog[open][aria-label="Voice note"]')
        no_open_dialogs()
        if evaluate('document.querySelectorAll(\'audio[src^="blob:"]\').length'):
            raise AssertionError('discarded_recording_audio_node_remains')
        if uploads:
            raise AssertionError('recording_was_unexpectedly_uploaded')
        report['checks']['recording_discarded_without_upload']=True
        report['privacy']['observed_upload_requests']=len(uploads)
        final=stats()
        limit=500 if args.playback_only else 2000
        if final['live_audio_tracks'] or final['capture_ms']>limit or (args.playback_only and prior_capture_ms+final['capture_ms']>1800) or final['safety_budget_triggered']:
            raise AssertionError('capture_lifetime_or_cleanup_limit')
        if not final['rms_samples']:
            raise ProbeGap('real_capture_meter_samples_unavailable')
        report['measurement']={**final,'capture_ms':round(final['capture_ms'],3),'max_rms':round(final['max_rms'],8)}
        report['phase']='complete'
        report['status']='PASS'
    except ProbeGap as error:
        report.update(status='PARTIAL',gap=str(error))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error_code=str(error) if str(error).isidentifier() else 'microphone_probe_failed_see_checks',error_detail=str(error)[:600])
    finally:
        if browser is not None:
            if instrumented:
                try:
                    final=evaluate('globalThis.__hermesMicReview.cleanup()')
                    report['cleanup']['device']={**final,'capture_ms':round(final['capture_ms'],3),'max_rms':round(final['max_rms'],8)}
                    report['cleanup']['all_tracks_ended']=final['live_audio_tracks']==0
                    report['cumulative_capture_ms']=round(prior_capture_ms+final['capture_ms'],3)
                    if final['live_audio_tracks']:
                        report['status']='FAIL'
                except Exception as error:
                    report['cleanup']['device_error']=type(error).__name__
                    report['status']='PARTIAL' if report['status']!='FAIL' else 'FAIL'
            if permission_overridden and original_browser_permission:
                try:
                    browser.pipe.call('Browser.setPermission', {'permission':{'name':'microphone'},'setting':original_browser_permission,'origin':ORIGIN,'embeddedOrigin':ORIGIN})
                    restored=evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)')
                    report['cleanup']['origin_microphone_permission_restored']=restored==original_browser_permission
                    if restored!=original_browser_permission:report['status']='FAIL'
                except Exception as error:
                    report['cleanup']['permission_restore_error']=type(error).__name__;report['status']='FAIL'
            if policy_changed and previous_policy is not None:
                try:
                    current=rpc(browser,'permissions.read',{'session_id':session})
                    rpc(browser,'permissions.update',{'session_id':session,'expected_version':current['version'],'mode':previous_policy['mode'],'capabilities':previous_policy['capabilities']})
                    restored=rpc(browser,'permissions.read',{'session_id':session})
                    report['cleanup']['server_policy_restored']=restored['mode']==previous_policy['mode'] and restored['capabilities']==previous_policy['capabilities']
                    if not report['cleanup']['server_policy_restored']:report['status']='FAIL'
                except Exception as error:
                    report['cleanup']['policy_restore_error']=type(error).__name__;report['status']='FAIL'
            if previous_view is not None:
                try:
                    rpc(browser,'view.write',{'state':previous_view})
                    # Reload discards remaining raw chunks/object URLs in this
                    # document; the browser is then closed, without exporting.
                    browser.call('Page.reload')
                    report['cleanup']['previous_view_restored']=True
                    report['cleanup']['recording_document_discarded']=True
                except Exception as error:
                    report['cleanup']['view_restore_error']=type(error).__name__;report['status']='FAIL'
            try:
                if browser.pipe:browser.pipe.on_event=previous_event
                browser.close();report['cleanup']['production_browser_closed']=True
            except Exception as error:
                report['cleanup']['browser_close_error']=type(error).__name__;report['status']='FAIL'
        save()
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'raw_audio_exported':False}))
    if report['status']=='FAIL':raise SystemExit(2)


if __name__=='__main__':
    main()
