"""Bounded production voice review using public speech, never ambient capture.

Preparation only until --execute-production-probe is explicitly supplied. Uses
the existing production pin, authenticated APIs and native window recorder. No
root, Qwen request, fake media, replacement response or isolated server. Newly
created records remain positively identified for the parent's scoped cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid


APP_ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/home/mani/mani-hermes-v5-6of3k6oz')
FIXTURE = Path('/home/mani/mani-hermes-v4-d1wzr5kx/private-state/voice-fixture/public-jfk.wav')
SAMPLE_SHA = '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e'
SAMPLE_BLOB = '3184d372cd2f8b804d3a540c70ec50d927b335d2'
REVISION = 'a8d002cfd879315632a579e73f0148d06959de36'
ORIGIN = 'http://127.0.0.1:18791'
MIC_OBSERVER = r'''(() => {
 const devices=navigator.mediaDevices, original=devices.getUserMedia;
 let calls=0;
 const wrapped=function(...args){calls++;return Reflect.apply(original,this,args)};
 devices.getUserMedia=wrapped;
 globalThis.__v5VoiceMic={calls:()=>calls,cleanup:()=>{
   if(devices.getUserMedia===wrapped)devices.getUserMedia=original;
 }};
})()'''


class ReviewGap(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=APP_ROOT)
    parser.add_argument('--output', type=Path, default=BASE/'review/voice')
    parser.add_argument('--fixture', type=Path, default=FIXTURE)
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe:
        parser.error('private proposal: parent review and an exclusive pin window are required before --execute-production-probe')
    if os.geteuid() == 0:
        raise RuntimeError('production_review_must_run_as_normal_operator')
    root = args.app_root.resolve(strict=True)
    sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_uploads import OBSERVE_UPLOADS
    from scripts.probe_v4_visual import (
        close_panels, enable_native_input, input_text,
        native_pointer_check, prepare, shot,
    )
    from workspace import launcher
    from workspace.capture import NativeWindowRecording

    if args.fixture.is_symlink() or args.fixture.stat().st_size > 2*1024*1024:
        raise ValueError('bounded_pinned_public_fixture_required')
    sample = args.fixture.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(sample)).encode()+b'\0'+sample).hexdigest()
    if digest(sample) != SAMPLE_SHA or blob != SAMPLE_BLOB:
        raise ValueError('pinned_public_speech_identity_mismatch')
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.is_symlink() or output.stat().st_mode & 0o077:
        raise ValueError('owner_only_review_directory_required')
    target = output/'voice.json'
    if target.exists():
        history = output/'history'
        history.mkdir(mode=0o700, exist_ok=True)
        previous = history/('attempt-'+str(time.time_ns())+'.json')
        previous.write_bytes(target.read_bytes())
        previous.chmod(0o600)
    sources = [
        'scripts/production_pin.py', 'scripts/probe_v4_chat.py',
        'scripts/probe_v4_uploads.py', 'scripts/probe_v4_visual.py',
        'workspace/capture.py', 'workspace/launcher.py', 'workspace/server.py',
        'workspace/voice.py', 'workspace/frontend/src/main.tsx',
        'workspace/frontend/src/recording.ts',
        'workspace/frontend/src/components/voice-note.tsx',
        'workspace/frontend/src/style.css',
    ]
    report = {
        'status': 'IN_PROGRESS', 'scope': 'actual production pin/profile/catalog on18791; pinned public speech sample',
        'sessions_created': [], 'attachments_created': [], 'checks': {}, 'cleanup': {}, 'captures': [],
        'privacy': {'ambient_microphone_capture': False, 'microphone_grant_requested': False,
                    'Qwen_inference_requested': False, 'playback_muted': True,
                    'raw_sample_audio_exported': False, 'original_user_content_exported': False,
                    'public_sample_transcript_visible_in_captures': True},
        'source_sha256': {name:digest((root/name).read_bytes()) for name in sources},
        'probe_sha256': digest(Path(__file__).read_bytes()),
        'public_sample': {'url':'https://github.com/ggml-org/whisper.cpp/blob/'+REVISION+'/samples/jfk.wav',
                          'revision':REVISION, 'git_blob_sha1':SAMPLE_BLOB,
                          'sha256':SAMPLE_SHA, 'bytes':len(sample)},
        'input': 'Native XTEST/compositor pointer after actual calibration; file input uses CDP DOM.setFileInputFiles, not a native file-picker audition.',
        'unverified': ['Physical microphone/device capture, listening and intelligibility are not exercised.',
                       'Late grant, device loss and recorder release are labelled source fixtures, not physical checks.',
                       'Human visual and continuous-motion approval remain pending.'],
    }

    def save():
        target.write_text(json.dumps(report, indent=2)+'\n')
        target.chmod(0o600)

    save()
    browser = recording = temporary = None
    initial_view = initial_draft = initial_filter = sound_storage = original_permission = None
    sounds_captured = False
    session = None
    observing = mic_observing = permission_changed = leave_open = owned_document = False
    filename = 'public-jfk.wav'
    voice = '#composer [data-slot="voice-note"]'

    def evaluate(source):
        return browser.evaluate(source)

    def click(selector):
        evaluate('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center",inline:"nearest"})')
        browser.click(selector)

    def count_attachments():
        return evaluate('document.querySelectorAll("#composer .attachment").length')

    def media():
        return evaluate('(()=>{const a=document.querySelector('+json.dumps(voice+' audio')+');return {time:a.currentTime,duration:Number.isFinite(a.duration)?a.duration:null,paused:a.paused,rate:a.playbackRate,muted:a.muted,volume:a.volume}})()')

    def detach_preserving_document():
        browser.pipe.call('Target.detachFromTarget', {'sessionId':browser.session})
        for descriptor in (browser.pipe.read, browser.pipe.write):
            os.close(descriptor)
        browser.pipe = None
        if browser.paused:
            signal.pidfd_send_signal(browser.owner, signal.SIGCONT)
            browser.paused = False
        os.close(browser.owner)
        browser.owner = None

    try:
        browser = ProductionPin()
        report['pin'] = browser.identity
        initial_view = rpc(browser, 'view.read', {})
        initial_filter = evaluate('document.querySelector(".rail-search input").value')
        # Never reload/close a document whose unsaved attachment objects we do
        # not own. No test record has been created at this point.
        if count_attachments():
            leave_open = True
            raise ReviewGap('preexisting_unsent_attachments_preserved')
        if initial_view.get('session_id'):
            initial_draft = rpc(browser, 'draft.read', {'session_id':initial_view['session_id']})
            try:
                browser.wait('document.querySelector("#prompt").value==='+json.dumps(initial_draft['text']))
            except (RuntimeError, TimeoutError):
                leave_open = True
                raise ReviewGap('existing_unsaved_draft_preserved')
        else:
            if evaluate('document.querySelector("#prompt").value'):
                leave_open = True
                raise ReviewGap('unowned_unsaved_input_preserved')
        nonce = 'v5-voice-'+uuid.uuid4().hex[:10]
        created = rpc(browser, 'session.create', {'project_id':None, 'arm':'normal'})
        session = created['id']
        report['sessions_created'].append(session)
        report['session_id'] = session
        report['verification_label'] = nonce
        save()
        rpc(browser, 'session.rename', {'session_id':session, 'title':nonce})
        selected = {**initial_view, 'session_id':session, 'project_id':None, 'arm':'normal', 'task_kind':'chat', 'motion':'system'}
        rpc(browser, 'view.write', {'state':selected})
        browser.reload_ready()
        browser.wait('!!document.querySelector("#prompt")&&!document.querySelector("#prompt").disabled')
        if count_attachments() or evaluate('document.querySelector("#prompt").value'):
            raise RuntimeError('new_owned_conversation_not_empty')
        owned_document = True
        prepare(browser)
        close_panels(browser)
        input_text(browser, '.rail-search input', nonce)
        browser.wait('document.querySelectorAll(".session-row").length===1&&document.querySelector(".session-row>button").textContent.includes('+json.dumps(nonce)+')')
        sound_storage = evaluate('localStorage.getItem("hermes-ui:sounds")')
        sounds_captured = True
        if evaluate('document.querySelector("#sound-toggle").dataset.sound==="on"'):
            click('#sound-toggle')
        report['native_pointer'] = native_pointer_check(browser)
        if report['native_pointer']['status'] != 'PASS':
            raise ReviewGap('native_pointer_not_qualified')
        enable_native_input(browser)
        report['served_app_js_sha256'] = evaluate("fetch('/assets/app.js',{cache:'no-store'}).then(r=>r.arrayBuffer()).then(b=>crypto.subtle.digest('SHA-256',b)).then(h=>Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join(''))")
        if report['served_app_js_sha256'] != digest((root/'workspace/ui/dist/app.js').read_bytes()):
            raise RuntimeError('served_build_not_current_checkout')

        # The browser is forced to denied first, and never granted. A broken
        # application gate therefore cannot start ambient capture during review.
        original_permission = evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)')
        if original_permission not in ('prompt', 'granted', 'denied'):
            raise ReviewGap('original_origin_microphone_permission_unknown')
        browser.pipe.call('Browser.setPermission', {'permission':{'name':'microphone'}, 'setting':'denied', 'origin':ORIGIN, 'embeddedOrigin':ORIGIN})
        permission_changed = True
        if evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)') != 'denied':
            raise ReviewGap('browser_denial_safety_fence_not_observable')
        policy = rpc(browser, 'permissions.read', {'session_id':session})
        if policy['capabilities']['microphone']:
            raise ReviewGap('new_owned_conversation_must_default_to_microphone_denied')
        evaluate(MIC_OBSERVER)
        mic_observing = True
        if evaluate('!!document.querySelector(\'[aria-label="Record voice note"]\')'):
            click('[aria-label="Record voice note"]')
        else:
            click('#plus-menu')
            evaluate('(()=>{const e=[...document.querySelectorAll(".action-menu button")].find(e=>e.textContent.includes("Record voice note"));if(!e)throw Error("record_action_missing");e.dataset.v5Voice="record"})()')
            click('[data-v5-voice="record"]')
        browser.wait('!!document.querySelector(".error-banner")&&!!document.querySelector(\'dialog[open][aria-label="Settings"]\')')
        calls = evaluate('globalThis.__v5VoiceMic.calls()')
        if calls != 0:
            raise RuntimeError('app_consent_denial_did_not_precede_getUserMedia')
        report['checks']['app_consent_denial_before_getUserMedia'] = {'calls':calls, 'microphone_policy':False, 'browser_safety_fence':'denied; never granted'}
        shot(browser, output, 'app-consent-denied', report['captures'], selector='.error-banner')
        close_panels(browser)

        capabilities = rpc(browser, 'capabilities.read', {})
        if not capabilities.get('attachments') or not capabilities.get('transcription'):
            raise ReviewGap('actual_CPU_transcription_unavailable')
        installation = json.loads((Path.home()/'.local/share/hermes-workspace/stt/installation.json').read_text())
        if installation.get('source_revision') != REVISION or installation.get('CPU_only') is not True:
            raise ReviewGap('installed_CPU_STT_provenance_not_current')
        report['CPU_transcription'] = {key:installation.get(key) for key in (
            'source_revision', 'CPU_only', 'files', 'model_repository', 'model_revision')}
        evaluate(OBSERVE_UPLOADS)
        observing = True
        temporary = tempfile.TemporaryDirectory(prefix='hermes-v5-voice-', dir=launcher.PROFILE.parent)
        directory = Path(temporary.name)
        directory.chmod(0o700)
        fixture = directory/filename
        fixture.write_bytes(sample)
        fixture.chmod(0o600)
        document = browser.call('DOM.getDocument')['root']['nodeId']
        file_input = browser.call('DOM.querySelector', {'nodeId':document, 'selector':'#composer input[type="file"]'})['nodeId']
        if not file_input:
            raise RuntimeError('actual_file_input_missing')
        started = time.monotonic()
        browser.call('DOM.setFileInputFiles', {'nodeId':file_input, 'files':[str(fixture)]})
        browser.wait('globalThis.__hermesUploadReview.summary().records.length===1', timeout=20)
        uploaded = evaluate('globalThis.__hermesUploadReview.summary().records[0]')
        report['attachments_created'].append(uploaded['id'])
        save()
        browser.wait('document.querySelectorAll("#composer .attachment").length===1', timeout=150)
        attachment = rpc(browser, 'attachment.metadata', {'id':uploaded['id']})
        metadata = attachment['metadata']
        transcript = metadata.get('transcript', '')
        waveform = metadata.get('waveform', [])
        duration = metadata.get('duration', 0)
        if attachment['sha256'] != SAMPLE_SHA or attachment['mime'] != 'audio/wav' or attachment['bytes'] != len(sample):
            raise RuntimeError('actual_public_upload_identity_mismatch')
        if metadata.get('method') != 'local_whisper_cpp_CPU' or not 10.9 <= duration <= 11.1 or len(waveform) != 40 or not all(type(v) in (int, float) and 0 <= v <= 1 for v in waveform) or not any(waveform) or 'ask not' not in ' '.join(transcript.lower().split()):
            raise RuntimeError('actual_CPU_transcription_waveform_or_duration_failed')
        report['checks']['actual_public_upload_CPU_transcription'] = {'id':attachment['id'], 'sha256':attachment['sha256'], 'bytes':attachment['bytes'], 'duration_seconds':duration, 'waveform_bars':len(waveform), 'waveform_peak':max(waveform), 'transcript_contains_ask_not':True, 'transcript_sha256':digest(transcript.encode()), 'observed_total_seconds':time.monotonic()-started}
        browser.wait('(()=>{const a=document.querySelector('+json.dumps(voice+' audio')+');return a&&a.readyState>=1&&!document.querySelector('+json.dumps(voice+' [data-slot="voice-note-control"]')+').disabled})()')
        evaluate('(()=>{const a=document.querySelector('+json.dumps(voice+' audio')+');a.muted=true;a.volume=0})()')
        # Native footage begins after CPU setup, remaining bounded by the proven
        # recorder's30-second hard cap. It captures only the owned app XID.
        recording_started = time.monotonic()
        recording = NativeWindowRecording(browser, output/'voice-playback-unedited.mp4')
        recording.hold(.35)
        shot(browser, output, 'voice-ready', report['captures'], selector='#composer')
        before = media()
        click(voice+' [aria-label="Play voice message"]')
        browser.wait('document.querySelector('+json.dumps(voice+' audio')+').currentTime>0.15')
        recording.hold(.65)
        playing = media()
        if playing['paused'] or playing['time'] <= before['time'] or not playing['muted'] or playing['volume'] != 0:
            raise RuntimeError('real_muted_playback_clock_did_not_advance')
        shot(browser, output, 'voice-playing', report['captures'], selector='#composer')
        click(voice+' [aria-label="Pause voice message"]')
        paused = media()
        recording.hold(.35)
        held = media()
        if not held['paused'] or abs(held['time']-paused['time']) > .08:
            raise RuntimeError('real_pause_did_not_hold_media_clock')
        rect = browser.rect(voice+' [aria-label="Seek"]')
        browser.mouse(rect['x']+rect['width']*.45, rect['y']+rect['height']/2)
        sought = media()
        if abs(sought['time']-duration*.45) > .6:
            raise RuntimeError('actual_waveform_pointer_seek_failed')
        click(voice+' [data-slot="voice-note-time"]')
        speed = media()
        if speed['rate'] != 1.5:
            raise RuntimeError('actual_speed_control_failed')
        shot(browser, output, 'voice-seek-speed', report['captures'], selector='#composer')
        click(voice+' [aria-label="Play voice message"]')
        recording.hold(.65)
        resumed = media()
        click(voice+' [aria-label="Pause voice message"]')
        if resumed['paused'] or resumed['time'] <= sought['time'] or resumed['rate'] != 1.5:
            raise RuntimeError('resumed_media_clock_or_speed_failed')
        recording.hold(.6)
        if time.monotonic()-recording_started > 28:
            raise ReviewGap('native_capture_budget_elapsed_before_complete_sequence')
        finished, recording = recording, None
        report['recording'] = finished.finish()
        report['checks']['actual_muted_play_pause_seek_speed'] = {'before':before, 'playing':playing, 'paused':paused, 'held':held, 'sought':sought, 'speed':speed, 'resumed':resumed}
        report['checks']['new_test_conversation_has_no_model_messages'] = rpc(browser, 'session.history', {'session_id':session}) == []
        report['checks']['no_microphone_requests'] = evaluate('globalThis.__v5VoiceMic.calls()') == 0
        if not report['checks']['new_test_conversation_has_no_model_messages'] or not report['checks']['no_microphone_requests']:
            raise RuntimeError('privacy_or_no_inference_contract_failed')
        report['status'] = 'PASS_SCOPED_TECHNICAL'
    except ReviewGap as error:
        report.update(status='PARTIAL', gap=str(error))
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__, error_code=str(error) if str(error).isidentifier() else 'voice_probe_failed_see_checks')
    finally:
        if recording:
            try:
                report['partial_recording'] = recording.finish()
            except Exception as error:
                report['recording_error'] = type(error).__name__
                report['status'] = 'FAIL'
        if browser:
            def cleanup_step(name, action):
                try:
                    result = action()
                    report['cleanup'][name] = True if result is None else result
                    if result is False:
                        report['status'] = 'FAIL'
                except Exception as error:
                    report['cleanup'][name] = {'error_type':type(error).__name__}
                    report['status'] = 'FAIL'

            def restore_permission():
                browser.pipe.call('Browser.setPermission', {'permission':{'name':'microphone'}, 'setting':original_permission, 'origin':ORIGIN, 'embeddedOrigin':ORIGIN})
                return evaluate('navigator.permissions.query({name:"microphone"}).then(p=>p.state)') == original_permission

            def remove_owned_upload():
                try:
                    rows = evaluate('globalThis.__hermesUploadReview.summary().records')
                    report['attachments_created'] = list(dict.fromkeys([*report['attachments_created'], *[r['id'] for r in rows if r['name'] == filename]]))
                    if evaluate('!!document.querySelector('+json.dumps(voice+' audio')+')'):
                        evaluate('document.querySelector('+json.dumps(voice+' audio')+').pause()')
                    remove = '#composer button[aria-label="Remove public-jfk.wav"]'
                    if evaluate('!!document.querySelector('+json.dumps(remove)+')'):
                        click(remove)
                    browser.wait('document.querySelectorAll("#composer .attachment").length===0')
                finally:
                    evaluate('globalThis.__hermesUploadReview.cleanup()')
                # Selection persistence belongs to the browser, not the RPC
                # schema. Reopen the same owned session after real UI removal:
                # an empty DOM after hydration proves no dangling selection ID.
                if rpc(browser, 'view.read', {})['session_id'] != session:
                    raise RuntimeError('attachment_cleanup_not_in_owned_session')
                browser.reload_ready()
                browser.wait('!!document.querySelector("#prompt")&&!document.querySelector("#prompt").disabled')
                return count_attachments() == 0

            def clear_new_draft():
                # Only type into a document already proved to be the new owned
                # session. Navigation failure must never clear the old draft.
                if owned_document:
                    input_text(browser, '#prompt', '')
                    evaluate('new Promise(resolve=>setTimeout(resolve,550))')
                rpc(browser, 'draft.write', {'session_id':session, 'text':'', 'mode':'chat'})
                return rpc(browser, 'draft.read', {'session_id':session})['text'] == ''

            def remove_microphone_observer():
                report['microphone_request_count'] = evaluate('globalThis.__v5VoiceMic.calls()')
                evaluate('globalThis.__v5VoiceMic.cleanup()')
                return report['microphone_request_count'] == 0

            def restore_sound():
                close_panels(browser)
                expected = sound_storage != 'off'
                if evaluate('document.querySelector("#sound-toggle").dataset.sound==="on"') != expected:
                    click('#sound-toggle')
                if sound_storage is None:
                    evaluate('localStorage.removeItem("hermes-ui:sounds")')
                else:
                    evaluate('localStorage.setItem("hermes-ui:sounds",'+json.dumps(sound_storage)+')')
                return evaluate('localStorage.getItem("hermes-ui:sounds")') == sound_storage

            def restore_view():
                rpc(browser, 'view.write', {'state':initial_view})
                browser.reload_ready()
                input_text(browser, '.rail-search input', initial_filter or '')
                if initial_draft is not None:
                    current = rpc(browser, 'draft.read', {'session_id':initial_view['session_id']})
                    report['cleanup']['existing_draft_preserved'] = current == initial_draft
                    if current != initial_draft:
                        return False
                return rpc(browser, 'view.read', {}) == initial_view

            # Each restoration is independent: a failed UI/card removal cannot
            # suppress browser-permission, existing-view or launcher recovery.
            if permission_changed:
                cleanup_step('origin_microphone_permission_restored', restore_permission)
            if mic_observing:
                cleanup_step('microphone_observer_removed_and_requests_zero', remove_microphone_observer)
            if observing:
                cleanup_step('owned_unsent_attachment_removed_and_absent_after_reload', remove_owned_upload)
            if session:
                cleanup_step('new_test_draft_cleared', clear_new_draft)
            if sounds_captured:
                cleanup_step('accepted_sound_preference_restored', restore_sound)
            if initial_view is not None and not leave_open:
                cleanup_step('initial_view_restored', restore_view)

            def restore_native():
                cursor = getattr(browser, '_native_initial_cursor', None)
                try:
                    if cursor:
                        subprocess.run(['/usr/bin/hyprctl', 'dispatch', f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'], capture_output=True, timeout=4, check=True)
                finally:
                    native = getattr(browser, '_native_input', None)
                    if native:
                        native.close()

            cleanup_step('native_input_and_cursor_restored', restore_native)
            if leave_open:
                cleanup_step('pin_left_open_to_preserve_unowned_unsent_state', detach_preserving_document)
            else:
                cleanup_step('production_browser_closed', browser.close)
        if temporary:
            temporary.cleanup()
            report['cleanup']['temporary_public_sample_copy_removed'] = True
        report['cleanup']['new_attachment_and_session_IDs_retained_for_parent_scoped_cleanup'] = True
        save()
    print(json.dumps({'status':report['status'], 'report':str(target), 'session_ids':report['sessions_created'], 'attachment_ids':report['attachments_created']}))
    if report['status'] != 'PASS_SCOPED_TECHNICAL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
