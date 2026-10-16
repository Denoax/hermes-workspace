"""Observe real v5 turns and CPU timing on the existing authenticated Hermes pin.

Send and Cancel use the actual UI. RPC calls only observe catalog/run state.
Callback timing is CPU evidence, never GPU timing or presented-frame cadence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_chat import rpc
from scripts.probe_v4_visual import close_panels, input_text
from scripts.performance_summary import summarize
from scripts.performance_capture import stop_performance
from workspace.chat import wait_for_normal_recovery
from workspace.server import normal_profile_unchanged
from workspace.capture import NativeWindowRecording

TERMINAL = {'completed', 'failed', 'cancelled'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--arm', choices=('normal', 'abliterated'), required=True)
    parser.add_argument('--turns', type=int, choices=(1, 3), default=3)
    parser.add_argument('--cancel', action='store_true')
    parser.add_argument('--record-cancel', action='store_true', help='Silent app-only unedited native capture, bounded by the existing 30-second recorder.')
    parser.add_argument('--reading-check', action='store_true', help='Observe actual growing-output reading position, terminal activity and Jump to latest during the cancellation case.')
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe or os.geteuid() == 0:
        parser.error('explicit normal-operator production execution required')
    if args.cancel and args.turns != 1:
        parser.error('cancellation is one owned turn')
    if args.record_cancel and not args.cancel:
        parser.error('native recording is scoped to the cancellation case')
    if args.reading_check and not args.cancel:
        parser.error('reading observation requires the owned cancellation case')
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = args.output / 'chat.json'
    if target.exists():
        raise RuntimeError('new_output_directory_required')
    report = {'status': 'IN_PROGRESS', 'arm': args.arm, 'cancel_case': args.cancel,
              'scope': 'actual production pin18791; no isolated server or replacement responses',
              'verification_word': 'maple-' + uuid.uuid4().hex[:8], 'runs': [],
              'timing_scope': 'UI click to polled public output/state; 0.5s polling plus RPC delay. Backend first_token_seconds starts in the worker before optional search/admission/tokenization and may first observe a tool fragment; backend total_seconds ends before native release/recovery. Cold model load is not separately measured.',
              'human_approval': None, 'cleanup': {}}
    browser = None
    initial = None
    sid = None
    active_run = None
    sampler_active = False
    leave_open = False
    recording = None

    def save():
        target.write_text(json.dumps(report, indent=2) + '\n')

    def mark(phase, run_id=None, basis='production_rpc_state', arm=None):
        fields = {'arm': arm or args.arm, 'phase': phase, 'run_id': run_id, 'basis': basis}
        browser.evaluate('globalThis.__hermesPerformanceProbe.mark(' + json.dumps(fields) + ')')

    try:
        browser = ProductionPin()
        report['pin'] = browser.identity
        report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        paths = ('workspace/frontend/src/main.tsx', 'workspace/frontend/src/style.css', 'workspace/frontend/src/controls.tsx',
                 'workspace/ui/dist/app.js', 'workspace/ui/dist/app.css', 'workspace/launcher.py', 'workspace/server.py', 'workspace/chat.py', 'scripts/performance_capture.py', 'scripts/performance_sampler.js',
                 'workspace/capture.py', 'workspace/native_coordinates.py', 'scripts/probe_v4_visual.py')
        report['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
        report['served_sha256'] = browser.evaluate('(async()=>{const out={};for(const name of ["app.js","app.css"]){const r=await fetch("/assets/"+name,{cache:"no-store"});if(!r.ok)throw Error("served_build_missing");out[name]=[...new Uint8Array(await crypto.subtle.digest("SHA-256",await r.arrayBuffer()))].map(v=>v.toString(16).padStart(2,"0")).join("")}return out})()')
        if any(report['served_sha256'][name] != report['source_sha256']['workspace/ui/dist/' + name] for name in ('app.js', 'app.css')):
            raise RuntimeError('actual_pin_served_build_mismatch')
        browser.wait('!!document.querySelector("#prompt")&&!document.querySelector("#prompt").disabled')
        initial = rpc(browser, 'view.read', {})
        saved_selection = browser.evaluate('(()=>{const raw=localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' ) + '+(' + json.dumps(initial.get('session_id')) + '??"new"));try{return raw!==null&&(!JSON.parse(raw)?.ids||JSON.parse(raw).ids.length>0)}catch{return true}})()')
        if saved_selection or browser.evaluate('document.querySelectorAll("#composer .attachment,.attachment-issues").length'):
            leave_open = True
            raise RuntimeError('unsent_attachments_require_preservation')
        draft = rpc(browser, 'draft.read', {'session_id': initial['session_id']}) if initial.get('session_id') else None
        if browser.evaluate('document.querySelector("#prompt").value') != (draft['text'] if draft else ''):
            leave_open = True
            raise RuntimeError('unsaved_prompt_requires_preservation')
        ready = rpc(browser, 'readiness.read', {})
        report['initial_readiness'] = ready
        if ready['state'] != 'ready' or not ready['models'][args.arm]['available']:
            raise RuntimeError('protected_model_admission_unavailable')
        inventory = rpc(browser, 'models.list', {})
        report['verified_installed_models'] = inventory
        existing_sessions = {row['id'] for row in rpc(browser, 'session.list', {})}
        # Operator setup creates one identified empty, project-free session.
        # It does not overwrite the user's separate "new conversation" draft.
        created = rpc(browser, 'session.create', {'project_id': None, 'arm': args.arm})
        sid = created['id']
        report['session_id'] = sid
        report['session_setup'] = 'operator catalog RPC; Send/history/cancel use actual UI, no fabricated messages'
        save()
        rpc(browser, 'session.rename', {'session_id': sid, 'title': report['verification_word']})
        rpc(browser, 'view.write', {'state': {**initial, 'project_id': None, 'session_id': sid, 'arm': args.arm, 'task_kind': 'chat'}})
        browser.reload_ready()
        browser.wait('document.querySelector("#prompt").value===""&&!document.querySelector(".message")')
        browser.evaluate('(()=>{const e=document.querySelector("#model-picker");e.value=' + json.dumps(args.arm) + ';e.dispatchEvent(new Event("change",{bubbles:true}))})()')
        input_text(browser, '.rail-search input', report['verification_word'])
        browser.evaluate('(' + (ROOT / 'scripts/performance_sampler.js').read_text() + ')({duration_ms:300000})')
        sampler_active = True
        mark('idle', basis='idle_observation', arm='none')
        # Quiet baseline, with a real harmless input/focus path during the same
        # sample. No response or status is injected into the application.
        browser.click('#prompt')
        time.sleep(5)
        word = report['verification_word']
        prompts = ([f'{word}: Write 60 short numbered lines about common trees. Use one sentence and one paragraph per line, starting with 1. Continue through 60.'] if args.reading_check else
                   [f'{word}: Count from 1 to 10000, one integer per line. Do not abbreviate.'] if args.cancel else
                   [f'Remember the harmless verification word {word}. Reply with only that word.',
                    'What exact verification word did I ask you to remember? Reply with only the word.',
                    'Reply with that same remembered verification word followed by :3. No other text.'][:args.turns])
        report['test_prompts'] = prompts
        save()
        for index, prompt in enumerate(prompts):
            if index:
                raw = stop_performance(browser)
                (args.output / f'performance-{index}.json').write_text(json.dumps(raw) + '\n')
                (args.output / f'performance-{index}-summary.json').write_text(json.dumps(summarize(raw), indent=2) + '\n')
                sampler_active = False
                browser.reload_ready()
                input_text(browser, '.rail-search input', word)
                browser.evaluate('(' + (ROOT / 'scripts/performance_sampler.js').read_text() + ')({duration_ms:300000})')
                sampler_active = True
            input_text(browser, '#prompt', prompt)
            browser.wait('!document.querySelector("#send").disabled')
            mark('ui_interaction', basis='trusted_UI_action')
            started = time.monotonic()
            browser.click('#send')
            digest = hashlib.sha256(prompt.encode()).hexdigest()
            result = {'prompt': prompt, 'states': [], 'stream_samples': [], 'observed_first_text_seconds': None}
            report['runs'].append(result)
            previous_state = None
            cancel_time = None
            last_progress = started
            interacted = False
            reading_anchor = None
            reading_last_chars = None
            while time.monotonic() - started < 240:
                candidate_sid = sid or rpc(browser, 'view.read', {}).get('session_id')
                if candidate_sid:
                    snap = rpc(browser, 'chat.snapshot', {'session_id': candidate_sid})
                    row = next((r for r in snap['runs'] if r['settings']['prompt_sha256'] == digest), None)
                    if row:
                        if candidate_sid in existing_sessions:
                            raise RuntimeError('owned_turn_not_in_new_session')
                        sid = candidate_sid
                        active_run = row['id']
                        report['session_id'] = sid
                        text = ''.join(m['text'] for m in snap['messages'] if m['role'] == 'assistant' and m.get('job') == active_run)
                        elapsed = time.monotonic() - started
                        if previous_state != row['state']:
                            mark(row['state'], active_run)
                            result['states'].append({'state': row['state'], 'seconds': elapsed})
                            previous_state = row['state']
                        if text and result['observed_first_text_seconds'] is None:
                            result['observed_first_text_seconds'] = elapsed
                            mark('streaming', active_run, 'production_stream_delta')
                        if text and (not result['stream_samples'] or result['stream_samples'][-1]['characters'] != len(text)):
                            result['stream_samples'].append({'seconds': elapsed, 'characters': len(text)})
                        if row['state'] == 'generating' and not interacted:
                            if args.record_cancel:
                                recording = NativeWindowRecording(browser, args.output / 'actual-stream-cancel-unedited.mp4')
                            # Native pointer geometry is covered separately;
                            # these browser-trusted panel inputs sample CPU
                            # feedback under the actual inference workload.
                            browser.click('#settings-toggle')
                            browser.key('Escape')
                            interacted = True
                        if args.reading_check and row['state'] == 'generating' and cancel_time is None:
                            metric = browser.evaluate('(()=>{const e=document.querySelector(".conversation");return {top:e.scrollTop,height:e.clientHeight,scroll_height:e.scrollHeight,jump:!!document.querySelector(".jump-latest")}})()')
                            if reading_anchor is None and metric['scroll_height']-metric['height'] >= 180:
                                rect = browser.rect('.conversation')
                                browser.call('Input.dispatchMouseEvent', {'type':'mouseWheel','x':rect['x']+rect['width']/2,
                                    'y':rect['y']+rect['height']/2,'deltaX':0,'deltaY':-10000})
                                browser.wait('document.querySelector(".conversation").scrollTop<=1')
                                reading_anchor = browser.evaluate('document.querySelector(".conversation").scrollTop')
                                reading_last_chars = len(text)
                                result['reading'] = {'status':'IN_PROGRESS','anchor_top':reading_anchor,'samples':[],
                                    'activity_count_before':len(snap.get('activity',[])),
                                    'input_scope':'Browser-trusted wheel and Jump click; not physical input.'}
                            elif reading_anchor is not None and len(text) > reading_last_chars:
                                if abs(metric['top']-reading_anchor)>1 or not metric['jump']:
                                    raise RuntimeError('actual_stream_changed_held_reading_position')
                                result['reading']['samples'].append({'characters':len(text),**metric})
                                reading_last_chars = len(text)
                        reading_ready = not args.reading_check or (reading_anchor is not None and len(result['reading']['samples'])>=3)
                        if args.cancel and reading_ready and len(text) >= 80 and len(result['stream_samples']) >= 2 and row['state'] == 'generating' and cancel_time is None:
                            close_panels(browser)
                            browser.wait('!!document.querySelector("#cancel-response")')
                            browser.capture(args.output / 'streaming-before-cancel.png')
                            mark('cancelling', active_run, 'trusted_UI_action')
                            browser.click('#cancel-response')
                            cancel_time = time.monotonic()
                        result.update(run=row, answer=text, activity=snap.get('activity', []), observed_total_seconds=elapsed)
                        save()
                        if row['state'] in TERMINAL:
                            if args.cancel:
                                if cancel_time is None or row['state'] != 'cancelled' or len(result['stream_samples']) < 2:
                                    raise RuntimeError('actual_growing_stream_and_compute_cancel_not_proven')
                                result['cancel_to_terminal_seconds'] = time.monotonic() - cancel_time
                                if args.reading_check:
                                    top = browser.evaluate('document.querySelector(".conversation").scrollTop')
                                    if abs(top-reading_anchor)>1:
                                        raise RuntimeError('terminal_activity_changed_held_reading_position')
                                    result['reading']['terminal_top'] = top
                                    result['reading']['activity_count_after'] = len(snap.get('activity',[]))
                                    browser.wait('!!document.querySelector(".jump-latest")')
                                    browser.click('.jump-latest')
                                    browser.wait('(()=>{const e=document.querySelector(".conversation");return e.scrollHeight-e.clientHeight-e.scrollTop<=2})()')
                                    result['reading'].update(status='PASS_SCOPED_TECHNICAL',jump_to_latest=True)

                            elif row['state'] != 'completed' or word not in text:
                                raise RuntimeError('real_reply_semantics_failed')
                            if row['identity']['arm'] != args.arm or row['identity']['context'] != (65536 if args.arm == 'normal' else 8192):
                                raise RuntimeError('native_model_identity_mismatch')
                            if len(snap['runs']) != index + 1 or len([m for m in snap['messages'] if m['role'] == 'user']) != index + 1:
                                raise RuntimeError('duplicate_turn_detected')
                            break
                if time.monotonic() - last_progress >= 10:
                    print(json.dumps({'arm': args.arm, 'turn': index + 1, 'state': previous_state, 'seconds': round(time.monotonic() - started)}), flush=True)
                    last_progress = time.monotonic()
                time.sleep(.5)
            else:
                raise TimeoutError('production_turn_deadline')
            browser.wait('!document.querySelector("#cancel-response")')
        if recording:
            recording.hold(.8)
            finished, recording = recording, None
            report['recording'] = finished.finish()
        raw = stop_performance(browser)
        (args.output / 'performance-final.json').write_text(json.dumps(raw) + '\n')
        (args.output / 'performance-final-summary.json').write_text(json.dumps(summarize(raw), indent=2) + '\n')
        sampler_active = False
        before_reload = rpc(browser, 'chat.snapshot', {'session_id': sid})
        browser.reload_ready()
        input_text(browser, '.rail-search input', word)
        browser.wait('!!document.querySelector(".message.assistant")')
        after_reload = rpc(browser, 'chat.snapshot', {'session_id': sid})
        if before_reload != after_reload:
            raise RuntimeError('history_changed_across_reload')
        report['reload_history_unchanged'] = True
        report['capture_navigation_filter'] = word
        browser.capture(args.output / 'production-final.png')
        report['status'] = 'PASS_SCOPED_TECHNICAL'
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__, error_code=str(error) if str(error).isidentifier() else 'production_probe_failed_see_runs')
        # This probe only enters owned verification content and never reads
        # credential values. Preserve its actionable selector/protocol failure.
        report['error_detail'] = str(error)[:300]
    finally:
        if recording:
            try:
                report['partial_recording'] = recording.finish()
            except Exception as error:
                report['cleanup']['recording_error'] = type(error).__name__
                report['status'] = 'FAIL'
        if browser:
            if sampler_active:
                try:
                    raw = stop_performance(browser)
                    (args.output / 'performance-final.json').write_text(json.dumps(raw) + '\n')
                    (args.output / 'performance-final-summary.json').write_text(json.dumps(summarize(raw), indent=2) + '\n')
                except Exception as error:
                    report['cleanup']['performance_error'] = type(error).__name__
                    report['status'] = 'FAIL'
            try:
                if active_run:
                    row = rpc(browser, 'chat.read', {'run_id': active_run})
                    if row['state'] not in TERMINAL:
                        rpc(browser, 'chat.cancel', {'run_id': active_run})
                report['normal_after'] = wait_for_normal_recovery(timeout=180)
                report['cleanup']['normal_context_and_configuration_unchanged'] = report['normal_after']['context'] == 65536 and normal_profile_unchanged()
                if not report['cleanup']['normal_context_and_configuration_unchanged']:
                    raise RuntimeError('normal_recovery_not_verified')
                if initial is not None and not leave_open:
                    rpc(browser, 'view.write', {'state': initial})
                    report['cleanup']['original_view_restored'] = rpc(browser, 'view.read', {}) == initial
                    if not report['cleanup']['original_view_restored']:
                        raise RuntimeError('original_view_restoration_failed')
            except Exception as error:
                report['cleanup']['recovery_error'] = type(error).__name__
                report['status'] = 'FAIL'
            finally:
                if leave_open:
                    browser.detach_preserving_document()
                else:
                    browser.close()
        save()
    print(json.dumps({'status': report['status'], 'session_id': sid, 'report': str(target)}), flush=True)
    if report['status'] != 'PASS_SCOPED_TECHNICAL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
