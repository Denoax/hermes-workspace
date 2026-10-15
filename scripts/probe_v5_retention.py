"""Production failure/reconnect/retry retention proposal; never a fixture server.

No execution until parent review, exclusive pin and authorized GPU window. Only
the existing user hermes-workspace.service is restarted. A is the original
candidate turn; B remains a newer unsent draft and attachment throughout retry.
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
TOTAL_SECONDS = 330
RECOVERY_RESERVE_SECONDS = 80
TERMINAL = {'completed', 'failed', 'cancelled'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main(phase_observer=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=APP_ROOT)
    parser.add_argument('--output', type=Path, default=BASE/'review/retention')
    parser.add_argument('--execute-production-probe', action='store_true')
    parser.add_argument('--gpu-window-authorized', action='store_true')
    args = parser.parse_args()
    if not (args.execute_production_probe and args.gpu_window_authorized):
        parser.error('private proposal: parent review, exclusive production pin and a separately authorized GPU window are required')
    if os.geteuid() == 0:
        raise RuntimeError('run_as_normal_operator_not_root')
    root = args.app_root.resolve(strict=True)
    sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_uploads import OBSERVE_UPLOADS
    from scripts.probe_v4_visual import input_text
    from workspace import launcher
    from workspace.chat import wait_for_normal_recovery
    from workspace.server import normal_profile_unchanged

    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.is_symlink() or output.stat().st_mode & 0o077:
        raise ValueError('private_review_directory_required')
    target = output/'retention.json'
    if target.exists():
        history = output/'history'
        history.mkdir(mode=0o700, exist_ok=True)
        prior = history/('attempt-'+str(time.time_ns())+'.json')
        prior.write_bytes(target.read_bytes())
        prior.chmod(0o600)
    files = ['scripts/production_pin.py', 'scripts/probe_v4_lifecycle.py',
             'scripts/probe_v4_chat.py', 'scripts/probe_v4_uploads.py',
             'workspace/chat.py', 'workspace/conversations.py',
             'workspace/catalog.py', 'workspace/attachments.py',
             'workspace/models.py', 'workspace/server.py',
             'workspace/frontend/src/main.tsx', 'workspace/production_client.py',
             'configs/backend-artifacts.lock.json', 'configs/normal-profile.lock.json']
    files.extend(str(path.relative_to(root)) for path in sorted((root/'workspace/frontend/src').rglob('*'))
                 if path.is_file() and path.suffix in ('.ts','.tsx','.css') and str(path.relative_to(root)) not in files)
    report = {'status':'IN_PROGRESS', 'scope':'actual production pin/profile/catalog18791; genuine user-app service interruption',
              'checks':{}, 'sessions_created':[], 'attachments_created':[], 'captures':[], 'samples':[],
              'service_restarts':[], 'phase_events':[], 'cleanup':{}, 'source_sha256':{f:digest((root/f).read_bytes()) for f in files},
              'probe_sha256':digest(Path(__file__).read_bytes()),
              'normal_profile_lock_sha256':digest((root/'configs/normal-profile.lock.json').read_bytes()),
              'privacy':{'original_user_draft_exported':False, 'microphone_or_audio_used':False},
              'budget':{'total_seconds':TOTAL_SECONDS, 'reserved_guard_recovery_seconds':RECOVERY_RESERVE_SECONDS},
              'performance_observer':'trusted parent callback' if phase_observer else 'not attached; no performance claim',
              'unverified':['Trusted browser pointer/file-input automation is not physical native-input review.',
                            'Normal restoration and protected admission must be measured; authorization flags do not bypass either.']}

    def save():
        target.write_text(json.dumps(report, indent=2)+'\n')
        target.chmod(0o600)

    save()
    started = time.monotonic()
    end = started+TOTAL_SECONDS
    work_end = end-RECOVERY_RESERVE_SECONDS
    browser = temporary = None
    initial_view = initial_draft = initial_filter = session = run_id = None
    owned_document = leave_open = False
    phase = 'initial_identity'
    last_progress = started
    nonce = 'v5-retention-'+uuid.uuid4().hex[:8]
    token_a, token_b = nonce+'-A', nonce+'-B'
    prompt_a = 'Reply with exactly '+token_a+'. The attached UTF-8 note is harmless verification context. No other text.'
    draft_b = 'Unsent follow-up draft '+token_b+'. Keep this draft unsent while retrying the earlier turn.'
    attachment_a = attachment_b = None

    def enter_phase(name):
        nonlocal phase
        phase = name
        event = {'phase':name, 'elapsed_seconds':time.monotonic()-started, 'run_id':run_id}
        report['phase_events'].append(event)
        save()
        # Narrow optional integration seam: a reviewed parent sampler can tag
        # its existing measurements. No CLI plugin or duplicate sampler is used.
        # The callback must be nonblocking and must not issue model/native calls.
        if phase_observer is not None and browser is not None:
            phase_observer(browser, dict(event))

    def progress():
        nonlocal last_progress
        if time.monotonic()-last_progress >= 10:
            print(json.dumps({'phase':phase, 'elapsed_seconds':round(time.monotonic()-started, 1)}), flush=True)
            last_progress = time.monotonic()

    def poll(callback, code, deadline=None):
        stop = min(work_end, deadline) if deadline else work_end
        while time.monotonic() < stop:
            value = callback()
            if value:
                return value
            progress()
            time.sleep(.25)
        raise TimeoutError(code)

    def snapshot():
        return rpc(browser, 'chat.snapshot', {'session_id':session})

    def answer(snap):
        return ''.join(m['text'] for m in snap['messages'] if m['role']=='assistant' and m.get('job')==run_id)

    def summary(run):
        return {key:run.get(key) for key in ('id','session','model','state','settings','created','error')}

    def click(selector):
        browser.evaluate('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center",inline:"nearest"})')
        browser.click(selector)

    def filter_owned():
        input_text(browser, '.rail-search input', nonce)
        browser.wait('document.querySelectorAll(".session-row").length===1&&[...document.querySelectorAll(".session-row>button:first-child,.folder-select>span")].every(e=>e.textContent.includes('+json.dumps(nonce)+'))')

    def reload():
        browser.reload_ready(timeout=min(30, max(1, work_end-time.monotonic())))
        filter_owned()
        browser.wait('document.querySelector(".session-row.selected>button")?.textContent.includes('+json.dumps(nonce)+')&&document.querySelector("#model-picker").value==="abliterated"')

    def capture(name):
        filter_owned()
        if rpc(browser, 'view.read', {})['session_id'] != session:
            raise RuntimeError('capture_not_in_owned_session')
        path = output/(name+'.png')
        browser.capture(path)
        report['captures'].append({'file':path.name, 'sha256':digest(path.read_bytes()), 'scope':'actual production own nonce-labelled session only'})

    def draft_matches(text, attachment):
        stored = rpc(browser, 'draft.read', {'session_id':session})
        chip = '#composer button[aria-label='+json.dumps('Remove '+attachment['name'])+']'
        ui = browser.evaluate('({text:document.querySelector("#prompt").value,chip:!!document.querySelector('+json.dumps(chip)+'),count:document.querySelectorAll("#composer .attachment").length})')
        canonical = rpc(browser, 'attachment.metadata', {'id':attachment['id']})
        return stored['text']==text and ui['text']==text and ui['chip'] and ui['count']==1 and all(canonical[k]==attachment[k] for k in ('id','name','sha256','bytes','mime'))

    def upload(letter):
        browser.evaluate(OBSERVE_UPLOADS)
        name = nonce+'-'+letter+'.txt'
        data = ('Harmless UTF-8 verification note\nverification_token='+nonce+'-'+letter+'\nUnicode: café, Ω.\n').encode()
        path = Path(temporary.name)/name
        path.write_bytes(data)
        path.chmod(0o600)
        document = browser.call('DOM.getDocument')['root']['nodeId']
        node = browser.call('DOM.querySelector', {'nodeId':document, 'selector':'#composer input[type="file"]'})['nodeId']
        if not node:
            raise RuntimeError('actual_file_input_missing')
        browser.call('DOM.setFileInputFiles', {'nodeId':node, 'files':[str(path)]})
        poll(lambda:browser.evaluate('globalThis.__hermesUploadReview.summary().records.length===1'), 'real_upload_response_missing', time.monotonic()+15)
        result = browser.evaluate('globalThis.__hermesUploadReview.summary().records[0]')
        report['attachments_created'].append(result['id'])
        save()
        metadata = rpc(browser, 'attachment.metadata', {'id':result['id']})
        if metadata['name'] != name or metadata['sha256'] != digest(data) or metadata['bytes'] != len(data) or metadata['mime'] != 'text/plain':
            raise RuntimeError('actual_uploaded_UTF8_identity_mismatch')
        return {k:metadata[k] for k in ('id','name','sha256','bytes','mime')}

    def restart_only_app(reason):
        if time.monotonic() >= work_end:
            raise TimeoutError('work_budget_exhausted_before_restart')
        command = ['/usr/bin/systemctl','show','hermes-workspace-runtime.service','-p','MainPID','--value']
        before_pid = int(subprocess.check_output(command, text=True, timeout=3).strip())
        subprocess.run(['/usr/bin/systemctl','--user','restart','hermes-workspace.service'], check=True, timeout=min(25, max(1, work_end-time.monotonic())))
        reload()
        after_pid = int(subprocess.check_output(command, text=True, timeout=3).strip())
        report['service_restarts'].append({'unit':'user/hermes-workspace.service', 'reason':reason, 'seconds':time.monotonic()-started, 'runtime_PID_before':before_pid, 'runtime_PID_after':after_pid})
        save()
        if before_pid <= 0 or after_pid <= 0 or before_pid == after_pid:
            raise RuntimeError('actual_application_runtime_did_not_restart')

    try:
        browser = ProductionPin()
        report['pin'] = browser.identity
        report['served_app_js_sha256'] = browser.evaluate("fetch('/assets/app.js',{cache:'no-store'}).then(r=>r.arrayBuffer()).then(b=>crypto.subtle.digest('SHA-256',b)).then(h=>Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join(''))")
        if report['served_app_js_sha256'] != digest((root/'workspace/ui/dist/app.js').read_bytes()):
            raise RuntimeError('served_build_not_current_checkout')
        initial_view = rpc(browser, 'view.read', {})
        initial_filter = browser.evaluate('document.querySelector(".rail-search input").value')
        if browser.evaluate('document.querySelectorAll("#composer .attachment").length'):
            leave_open = True
            raise RuntimeError('unowned_unsent_attachments_preserved_probe_not_started')
        if initial_view.get('session_id'):
            initial_draft = rpc(browser, 'draft.read', {'session_id':initial_view['session_id']})
            try:
                browser.wait('document.querySelector("#prompt").value==='+json.dumps(initial_draft['text']))
            except (RuntimeError, TimeoutError):
                leave_open = True
                raise RuntimeError('unowned_unsaved_draft_preserved_probe_not_started')
        elif browser.evaluate('document.querySelector("#prompt").value'):
            leave_open = True
            raise RuntimeError('unowned_unsaved_input_preserved_probe_not_started')
        report['normal_before'] = wait_for_normal_recovery(timeout=min(15, max(1, work_end-time.monotonic())))
        if not normal_profile_unchanged():
            raise RuntimeError('normal_configuration_drift_before_test')
        ready = rpc(browser, 'readiness.read', {})
        if ready['state'] != 'ready' or not ready.get('models', {}).get('abliterated', {}).get('available'):
            raise RuntimeError('protected_production_candidate_admission_unavailable')
        report['verified_linked_models'] = rpc(browser, 'models.list', {})
        created = rpc(browser, 'session.create', {'project_id':None,'arm':'abliterated'})
        session = created['id']
        report.update(session_id=session, verification_label=nonce, prompt_A_sha256=digest(prompt_a.encode()), draft_B_sha256=digest(draft_b.encode()), token_A=token_a, token_B=token_b)
        report['sessions_created'].append(session)
        save()
        rpc(browser, 'session.rename', {'session_id':session,'title':nonce})
        rpc(browser, 'view.write', {'state':{**initial_view,'project_id':None,'session_id':session,'arm':'abliterated','task_kind':'chat'}})
        reload()
        if snapshot()['runs'] or browser.evaluate('document.querySelector("#prompt").value') or browser.evaluate('document.querySelectorAll("#composer .attachment").length'):
            raise RuntimeError('new_owned_session_not_empty')
        owned_document = True
        temporary = tempfile.TemporaryDirectory(prefix='hermes-v5-retention-', dir=launcher.PROFILE.parent)
        Path(temporary.name).chmod(0o700)
        enter_phase('draft_A_reload')
        attachment_a = upload('A')
        input_text(browser, '#prompt', prompt_a)
        poll(lambda:draft_matches(prompt_a, attachment_a), 'draft_A_not_flushed')
        reload()
        poll(lambda:draft_matches(prompt_a, attachment_a), 'draft_A_or_attachment_not_retained_on_reload', time.monotonic()+8)
        report['checks']['initial_draft_A_and_selection_survive_reload'] = True
        capture('draft-A-restored')
        enter_phase('genuine_failure_A')
        browser.wait('!document.querySelector("#send").disabled')
        click('#send')
        def find_run():
            snap = snapshot()
            return next((r for r in snap['runs'] if r['settings']['prompt_sha256']==digest(prompt_a.encode())), None)
        run = poll(find_run, 'A_not_admitted', time.monotonic()+15)
        run_id = run['id']
        report['run_id'] = run_id
        save()
        snap = snapshot()
        if answer(snap) or run['state'] in TERMINAL:
            raise RuntimeError('before_public_output_restart_gate_missed')
        report['before_first_restart'] = summary(run)
        restart_only_app('genuine active A interruption before public output')
        def failed_ready():
            snap = snapshot()
            row = next(r for r in snap['runs'] if r['id']==run_id)
            if answer(snap):
                raise RuntimeError('A_got_public_output_before_failure')
            return row if row['state']=='failed' and rpc(browser,'readiness.read',{})['state']=='ready' else None
        failed = poll(failed_ready, 'failed_A_and_ready_not_observed')
        if 'Service restarted' not in (failed.get('error') or ''):
            raise RuntimeError('genuine_service_restart_failure_not_identified')
        report['genuine_failed_A'] = summary(failed)
        save()
        enter_phase('unsent_B_second_restart')
        attachment_b = upload('B')
        input_text(browser, '#prompt', draft_b)
        poll(lambda:draft_matches(draft_b, attachment_b), 'draft_B_not_flushed')
        restart_only_app('failed A with newer B draft and selection unsent')
        poll(lambda:draft_matches(draft_b, attachment_b), 'B_draft_or_selection_lost_after_second_restart', time.monotonic()+8)
        if snapshot()['runs'][0]['state'] != 'failed':
            raise RuntimeError('A_changed_while_B_was_unsent')
        report['checks']['B_text_chip_and_canonical_metadata_survive_second_restart'] = True
        capture('draft-B-after-second-restart')
        enter_phase('retry_original_A')
        poll(lambda:rpc(browser,'readiness.read',{})['state']=='ready', 'production_not_ready_before_retry')
        browser.wait('[...document.querySelectorAll("button")].some(e=>e.textContent.trim()==="Retry this turn"&&!e.disabled)')
        browser.evaluate('(()=>{const rows=[...document.querySelectorAll("button")].filter(e=>e.textContent.trim()==="Retry this turn"&&!e.disabled);if(rows.length!==1)throw Error("ambiguous_retry");rows[0].dataset.v5Retention="retry"})()')
        click('[data-v5-retention="retry"]')
        def acknowledged():
            row = next(r for r in snapshot()['runs'] if r['id']==run_id)
            return row if row['created'] != failed['created'] else None
        retried = poll(acknowledged, 'retry_acknowledgement_not_observed', time.monotonic()+15)
        report['retry_acknowledged'] = summary(retried)
        def terminal():
            snap = snapshot()
            row = next(r for r in snap['runs'] if r['id']==run_id)
            text = answer(snap)
            if not report['samples'] or report['samples'][-1]['characters'] != len(text):
                report['samples'].append({'seconds':time.monotonic()-started,'state':row['state'],'characters':len(text)})
                save()
            return (snap,row,text) if row['state'] in TERMINAL else None
        snap, completed, text = poll(terminal, 'retry_A_terminal_deadline')
        if completed['state'] != 'completed' or token_a not in text or token_b in text:
            raise RuntimeError('original_A_reply_semantics_failed')
        users = [m for m in snap['messages'] if m['role']=='user']
        associated = snap['attachments'].get(run_id, [])
        if len(snap['runs']) != 1 or len(users) != 1 or digest(users[0]['text'].encode()) != digest(prompt_a.encode()) or completed['settings']['attachments'] != [attachment_a['id']] or [a['id'] for a in associated] != [attachment_a['id']] or any(a['id']==attachment_b['id'] for rows in snap['attachments'].values() for a in rows):
            raise RuntimeError('retry_duplicated_turn_or_replaced_A_with_B_attachment')
        poll(lambda:draft_matches(draft_b, attachment_b), 'retry_consumed_or_changed_unsent_B', time.monotonic()+8)
        reload()
        poll(lambda:draft_matches(draft_b, attachment_b), 'B_lost_on_reload_after_A_retry', time.monotonic()+8)
        after = snapshot()
        if len(after['runs']) != 1 or after['runs'][0]['id'] != run_id or len([m for m in after['messages'] if m['role']=='user']) != 1 or answer(after) != text:
            raise RuntimeError('completed_A_history_not_retained_after_reload')
        report['checks']['same_run_one_user_message_original_A_attachment_and_reply'] = True
        report['checks']['newer_B_remains_unsent_through_retry_and_reload'] = True
        report['final_run'] = summary(completed)
        report['answer_sha256'] = digest(text.encode())
        report['attachments'] = {'A':attachment_a,'B':attachment_b}
        capture('retry-A-completed-B-unsent')
        report['status'] = 'PASS_SCOPED_TECHNICAL'
    except Exception as error:
        report.update(status='FAIL', phase=phase, error_type=type(error).__name__, error_code=str(error) if str(error).isidentifier() else 'retention_probe_failed_see_checks')
        if browser and owned_document:
            try:
                capture('failure-'+phase)
            except Exception as capture_error:
                report['failure_capture_error'] = type(capture_error).__name__
    finally:
        try:
            enter_phase('owned_cancel_and_normal_guard_recovery')
        except Exception as error:
            report['cleanup']['phase_observer_error'] = type(error).__name__
            report['status'] = 'FAIL'
        if browser and run_id:
            try:
                row = next(r for r in snapshot()['runs'] if r['id']==run_id)
                if row['state'] not in TERMINAL:
                    rpc(browser, 'chat.cancel', {'run_id':run_id})
                    report['cleanup']['only_owned_active_run_cancel_requested'] = True
            except Exception as error:
                report['cleanup']['owned_cancel_error'] = type(error).__name__
                report['status'] = 'FAIL'
        if browser and not leave_open:
            try:
                report['normal_after'] = wait_for_normal_recovery(timeout=max(1, end-time.monotonic()))
                pins = json.loads((root/'configs/normal-profile.lock.json').read_text())
                report['cleanup']['normal_context_65536_and_four_pins'] = report['normal_after']['context']==65536 and len(pins)==4 and normal_profile_unchanged()
                report['normal_configuration_sha256_values'] = sorted(pins.values())
                if not report['cleanup']['normal_context_65536_and_four_pins']:
                    report['status'] = 'FAIL'
            except Exception as error:
                report['cleanup']['normal_guard_recovery_error'] = type(error).__name__
                report['status'] = 'FAIL'
            try:
                if initial_view is not None:
                    rpc(browser, 'view.write', {'state':initial_view})
                    browser.reload_ready(timeout=15)
                    input_text(browser, '.rail-search input', initial_filter or '')
                    report['cleanup']['initial_view_restored'] = rpc(browser,'view.read',{})==initial_view
                    if initial_draft is not None:
                        report['cleanup']['existing_draft_preserved'] = rpc(browser,'draft.read',{'session_id':initial_view['session_id']})==initial_draft
                if any(v is False for v in report['cleanup'].values()):
                    report['status'] = 'FAIL'
            except Exception as error:
                report['cleanup']['view_restoration_error'] = type(error).__name__
                report['status'] = 'FAIL'
        if browser:
            try:
                if leave_open:
                    browser.pipe.call('Target.detachFromTarget', {'sessionId':browser.session})
                    for fd in (browser.pipe.read,browser.pipe.write):
                        os.close(fd)
                    browser.pipe = None
                    if browser.paused:
                        signal.pidfd_send_signal(browser.owner,signal.SIGCONT)
                        browser.paused = False
                    os.close(browser.owner)
                    browser.owner = None
                    report['cleanup']['pin_left_open_to_preserve_unowned_unsent_state'] = True
                else:
                    browser.close()
                    report['cleanup']['production_browser_closed'] = True
            except Exception as error:
                report['cleanup']['browser_error'] = type(error).__name__
                report['status'] = 'FAIL'
        if temporary:
            temporary.cleanup()
            report['cleanup']['harmless_fixture_tempfiles_removed'] = True
        report['cleanup']['new_A_message_and_unsent_B_retained_for_parent_scoped_cleanup'] = bool(session)
        report['total_observed_seconds'] = time.monotonic()-started
        save()
    print(json.dumps({'status':report['status'],'report':str(target),'sessions':report['sessions_created'],'attachments':report['attachments_created']}))
    if report['status'] != 'PASS_SCOPED_TECHNICAL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
