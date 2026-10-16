"""Composable native-window motion acquisition; no pin creation or approval.

Read and apply $reference-led-design. Runtime helpers are imported only when
called by the root-owned existing production pin. Raw failed/private media stays
in private staging; only unchanged positively guarded clips enter review output.
"""
import hashlib
import json
from pathlib import Path
import re
import signal
import threading
import time
import traceback

CLIP_CAP_SECONDS = 24


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def attachment_proof(receipt):
    proof = receipt.get('checks', {}).get('A_genuine_UTF8_draft_and_attachment')
    if proof is None:
        proof = receipt.get('resumed_from', {}).get('checks', {}).get('A_genuine_UTF8_draft_and_attachment')
    if proof is None and receipt.get('kind') == 'actual_interaction_subcheck_aggregate':
        row = receipt.get('subchecks', {}).get('A_genuine_UTF8_draft_and_attachment', {})
        require(row.get('outcome') == 'PASS', 'actual_A_attachment_subcheck_required')
        proof = row.get('value')
    require(isinstance(proof, dict) and all(key in proof for key in ('id', 'name', 'mime', 'bytes', 'sha256', 'draft_sha256')),
            'actual_harmless_attachment_and_draft_receipt_required')
    require(isinstance(proof['id'], str) and re.fullmatch('[a-f0-9]{32}', proof['id']), 'exact_owned_attachment_ID_required')
    return proof


def verify_aggregate_bytes(receipt, path):
    """Bind referenced measured values to unchanged original adverse receipts."""
    if receipt.get('kind') != 'actual_interaction_subcheck_aggregate':
        return {'status': 'NOT_APPLICABLE', 'kind': 'single interaction receipt'}
    base = path.parent.resolve(strict=True)
    originals = []
    for record in receipt['receipts']:
        loaded = {}
        for field, hash_field in (('artifact', 'sha256'), ('run_artifact', 'run_sha256')):
            target = base / record[field]
            require(not any(p.is_symlink() for p in (target, *target.parents)) and target.is_file()
                    and target.resolve().is_relative_to(base) and target.stat().st_size <= 1024 * 1024,
                    'bounded_unchanged_original_interaction_artifact_required')
            raw = target.read_bytes()
            require(sha(raw) == record[hash_field], 'original_interaction_receipt_bytes_changed')
            loaded[field] = json.loads(raw)
        require(loaded['artifact']['case']['nonce'] == receipt['case']['nonce']
                and loaded['artifact']['case']['records']['A']['id'] == receipt['case']['records']['A']['id']
                and loaded['run_artifact']['status'] == record['overall_status']
                and loaded['run_artifact']['source_sha256_before'] == record['source_sha256'],
                'original_interaction_identity_or_adverse_status_changed')
        originals.append(loaded['artifact'])
    for name, row in receipt['subchecks'].items():
        require(originals[row['source_receipt']].get('checks', {}).get(name) == row['value'],
                'aggregate_value_differs_from_original_measured_subcheck')
    return {'status': 'PASS', 'unchanged_original_receipts': len(originals),
            'unchanged_measured_subchecks': len(receipt['subchecks']),
            'whole_sequence_promoted_to_PASS': False}


def privacy_guard(owner, receipt):
    """No raw text/selection is returned to a public report."""
    from scripts.owned_v6_interactions import selection_ids
    case = owner.case
    a = owner.guard('A')
    proof = attachment_proof(receipt)
    draft = owner.rpc('draft.read', {'session_id': a['id']})
    expected = (case['nonce'] + ' unsent A draft; never submit this verification text.').encode()
    require(draft.get('mode') == 'chat' and sha(draft.get('text', '').encode()) == proof['draft_sha256'] == sha(expected),
            'later_private_A_draft_preserved_not_captured')
    state = owner.rpc('chat.snapshot', {'session_id': a['id']})
    require(not state['messages'] and not state['runs'] and not owner.rpc('session.jobs', {'session_id': a['id']}),
            'later_A_history_or_activity_preserved_not_captured')
    metadata = owner.rpc('attachment.metadata', {'id': proof['id']})
    require(all(metadata[key] == proof[key] for key in ('id', 'name', 'mime', 'bytes', 'sha256')),
            'later_attachment_metadata_preserved_not_captured')
    expected_payload = ('Harmless UTF-8 context for ' + case['nonce'] + ': maple, café, 你好.\n').encode()
    require(metadata['sha256'] == sha(expected_payload) and metadata['bytes'] == len(expected_payload),
            'only_original_harmless_UTF8_attachment_may_be_captured')
    selected = owner.b.evaluate('localStorage.getItem(' + json.dumps('hermes:draft-attachments:v1:' + a['id']) + ')')
    require(selection_ids(selected) == [proof['id']], 'later_attachment_selection_preserved_not_captured')
    require(owner.b.evaluate("document.querySelector('.rail-search input').value===" + json.dumps(case['nonce']) + "&&"
                            "[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')].every(e=>e.textContent.startsWith(" + json.dumps(case['nonce'] + ' · ') + '))'),
            'nonce_only_navigation_required_for_motion')
    owner.assert_a()
    return {'status': 'PASS', 'A_history_empty': True, 'original_harmless_draft_sha256': proof['draft_sha256'],
            'original_harmless_attachment_sha256': proof['sha256'], 'private_text_exported': False}


class ClipWatchdog:
    """Stop only the exact recorder child before its built-in30s ceiling."""
    def __init__(self, process, seconds=CLIP_CAP_SECONDS, timer_factory=threading.Timer):
        require(0 < seconds <= CLIP_CAP_SECONDS, 'bounded_clip_watchdog_required')
        self.process, self.fired = process, False
        def stop():
            self.fired = True
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGINT)
        self.timer = timer_factory(seconds, stop)
        self.timer.daemon = True

    def start(self):
        self.timer.start()

    def close(self):
        self.timer.cancel()
        self.timer.join(timeout=2)
        require(not self.timer.is_alive(), 'recorder_watchdog_did_not_join')


def record_clip(browser, surface, owner, receipt, root, output, private_staging, appearance):
    """Record actual controls at natural speed; preserve errors and source scope."""
    require(appearance in ('dark', 'light'), 'fixed_motion_theme_required')
    from scripts.probe_v4_visual import move, pointer_state
    from scripts.v6_surface_review import require_owned_native_focus, viewport
    from scripts.performance_summary import summarize
    from workspace.capture import NativeWindowRecording
    output, private_staging = Path(output), Path(private_staging)
    require('private-state' in private_staging.parts, 'private_motion_staging_required')
    private_staging.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = private_staging / (appearance + '-native-unedited.mp4')
    require(not path.exists(), 'preserve_previous_motion_attempt')
    report = {'status': 'IN_PROGRESS', 'theme': appearance, 'stages': [], 'media_exportable': False,
              'scope': 'Actual native app-XID only; silent, unedited normal-speed acquisition; synthesized native input.',
              'human_continuous_motion_approval': 'UNVERIFIED', 'GPU_or_presented_frame_timings': 'UNMEASURED'}
    recording = watchdog = None
    sampler_started = False
    started = time.monotonic()
    sampler = root / 'scripts/performance_sampler.js'
    def remaining():
        value = CLIP_CAP_SECONDS - (time.monotonic() - started)
        require(value > .5, 'motion_timeline_reached_recording_cap')
        return value
    def wait(expression):
        browser.wait(expression, timeout=min(3, remaining()))
    def hold(seconds):
        require(0 <= seconds <= 1 and seconds < remaining(), 'bounded_natural_motion_hold_required')
        recording.hold(seconds)
    def stage(name):
        require(re.fullmatch('[a-z][a-z0-9_]{0,60}', name), 'fixed_motion_stage_required')
        require_owned_native_focus(browser)
        require(browser.evaluate('document.visibilityState') == 'visible', 'visible_owned_document_required_for_motion')
        report['stages'].append({'name': name, 'wall_seconds': time.monotonic() - started,
                                 'browser_elapsed_ms': browser.evaluate('performance.now()')})
    def close():
        surface.key('Escape')
        wait('!document.querySelector("dialog[open],.anchored-popover")')
    try:
        surface.close()
        report['privacy_before'] = privacy_guard(owner, receipt)
        report['viewport'] = viewport(browser)
        require(report['viewport']['innerWidth'] >= 1000 and report['viewport']['innerHeight'] >= 650,
                'desktop_native_motion_viewport_required')
        report['reduced_motion'] = browser.evaluate('document.documentElement.dataset.motion')
        report['reduced_motion_system'] = browser.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')
        # Respect current preferences. Reduced motion is labelled, never disabled
        # solely to make an animation appear or manufacture parity evidence.
        recording = NativeWindowRecording(browser, path)
        watchdog = ClipWatchdog(recording.process); watchdog.start()
        browser.evaluate('(' + sampler.read_text() + ')({duration_ms:26000})')
        sampler_started = True
        report['sampler_sha256'] = sha(sampler.read_bytes())
        browser.evaluate('globalThis.__hermesPerformanceProbe.mark({arm:"none",basis:"idle_observation",phase:"idle",run_id:null})')
        stage('idle'); hold(.4)
        browser.evaluate('globalThis.__hermesPerformanceProbe.mark({arm:"none",basis:"trusted_UI_action",phase:"ui_interaction",run_id:null})')
        stage('plus_open_close_reopen')
        surface.click('#plus-menu'); wait('!!document.querySelector("#composer-actions")'); hold(.55)
        close(); hold(.25)
        surface.click('#plus-menu'); wait('!!document.querySelector("#composer-actions")'); hold(.12)
        close(); hold(.3)
        stage('effort_panel_open_close')
        surface.click('#effort-toggle'); wait('!!document.querySelector("#effort-options")'); hold(.6)
        close(); hold(.3)
        stage('settings_entry_exit_and_interruption')
        surface.click('#settings-toggle'); wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]\')'); hold(.7)
        close(); hold(.035)
        surface.click('#settings-toggle'); wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]\')'); hold(.035)
        close(); hold(.035)
        surface.click('#settings-toggle'); wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]\')'); hold(.6)
        close(); hold(.3)
        stage('files_details_alternation')
        for trigger, label, seconds in (('#files-toggle', 'Files', .55), ('#diagnostics', 'Details', .55),
                                         ('#files-toggle', 'Files', .08), ('#diagnostics', 'Details', .08),
                                         ('#files-toggle', 'Files', .5)):
            surface.click(trigger)
            selector = 'dialog[open][aria-label=' + json.dumps(label) + ']'
            wait('!!document.querySelector(' + json.dumps(selector) + ')')
            require(browser.evaluate('!document.querySelector("dialog:modal")'), 'useful_desktop_sheet_expected_for_alternation_clip')
            hold(seconds)
        close(); hold(.3)
        stage('row_menu_open_close_reopen')
        trigger = '#conversation-options-' + surface.target
        browser.evaluate('document.querySelector(' + json.dumps(trigger) + ').scrollIntoView({block:"nearest"})')
        surface.click(trigger); wait('!!document.querySelector("#row-actions")'); hold(.55)
        close(); hold(.035)
        surface.click(trigger); wait('!!document.querySelector("#row-actions")'); hold(.1)
        close(); hold(.35)
        stage('owned_delete_review_escape_reopen')
        for seconds in (.55, .08):
            surface.click(trigger); wait('!!document.querySelector("#row-actions")')
            surface.key('End'); surface.key('Return')
            wait('!!document.querySelector(\'dialog[open][aria-label="Delete conversation"]\')')
            hold(seconds)
            close(); hold(.1)
        stage('owned_buddy_follow_reverse_drag_cancel')
        buddy = browser.rect('#theme-buddy'); width = report['viewport']['innerWidth']; height = report['viewport']['innerHeight']
        cy = buddy['y'] + buddy['height'] / 2
        for x, y in ((20, 40), (width - 20, 40), (width - 20, height - 20), (20, height - 20)):
            require_owned_native_focus(browser); move(browser, x, y); hold(.2)
        for x in (20, width / 3, 2 * width / 3, width - 20, 2 * width / 3, width / 3, 20):
            require_owned_native_focus(browser); move(browser, x, cy); hold(.06)
        cx = buddy['x'] + buddy['width'] / 2
        before_theme = browser.evaluate('document.documentElement.dataset.theme')
        require_owned_native_focus(browser); pointer_state(browser, cx, cy, True); hold(.1)
        require_owned_native_focus(browser); move(browser, cx + 12, cy); hold(.12)
        require_owned_native_focus(browser); pointer_state(browser, cx + 12, cy, False); hold(.5)
        require(browser.evaluate('document.documentElement.dataset.theme') == before_theme, 'buddy_drag_cancel_changed_theme')
        surface.close()
        require_owned_native_focus(browser)
        report['privacy_after'] = privacy_guard(owner, receipt)
        report['status'] = 'CAPTURED_TECHNICAL_ONLY'
    except Exception as error:
        code = str(error)
        report.update(status='FAIL', error_category=type(error).__name__,
                      error_code=code if re.fullmatch('[A-Za-z0-9_:;.-]{1,256}', code) else 'see_private_outer_error')
        diagnostic = {'traceback': traceback.format_exc(), 'last_stage': report['stages'][-1]['name'] if report['stages'] else None}
        try:
            diagnostic['surface_state'] = browser.evaluate('''(()=>({
              dialogs:[...document.querySelectorAll('dialog')].map(e=>({open:e.open,label:e.getAttribute('aria-label'),modal:e.matches(':modal')})),
              active:{tag:document.activeElement?.tagName,id:document.activeElement?.id},
              keys:window.__v6SurfaceKeyReview,visibility:document.visibilityState
            }))()''')
        except Exception as diagnostic_error:
            diagnostic['snapshot_error_category'] = type(diagnostic_error).__name__
        diagnostic_path = private_staging / (appearance + '-failure.json')
        diagnostic_path.write_text(json.dumps(diagnostic, indent=2) + '\n'); diagnostic_path.chmod(0o600)
        report['private_diagnostic'] = {'file': diagnostic_path.name, 'sha256': sha(diagnostic_path.read_bytes()), 'exportable': False}
        raise
    finally:
        report['cleanup'] = {}
        def cleanup(name, callback):
            try:
                callback(); report['cleanup'][name] = {'status': 'ok'}
            except Exception as error:
                report['cleanup'][name] = {'status': 'failed', 'error_category': type(error).__name__}
                report['status'] = 'FAIL'
        if watchdog:
            cleanup('watchdog', watchdog.close)
            report['watchdog_fired'] = watchdog.fired
        if recording:
            def finish_recording():
                report['recording'] = recording.finish()
            cleanup('recording', finish_recording)
        if sampler_started:
            def stop_sampler():
                raw = browser.evaluate('globalThis.__hermesPerformanceProbe.stop("caller")')
                report['cpu_summary'] = summarize(raw)
                cpu_path = output / (appearance + '-cpu-raw.json')
                cpu_path.write_text(json.dumps(raw, indent=2) + '\n'); cpu_path.chmod(0o600)
                report['cpu_raw'] = {'file': cpu_path.name, 'sha256': sha(cpu_path.read_bytes()),
                                     'scope': 'Whole-app CPU/browser callbacks during native recording and synthetic interaction; no GPU, display cadence or physical input-to-photon measurement.'}
            cleanup('performance_sampler', stop_sampler)
        if report.get('status') == 'CAPTURED_TECHNICAL_ONLY':
            def publish_guarded_media():
                require_owned_native_focus(browser)
                report['privacy_after_capture'] = privacy_guard(owner, receipt)
                require(not report.get('watchdog_fired') and 0 < report['recording']['seconds'] < 30,
                        'motion_capture_was_truncated_or_not_under_30_seconds')
                staged_files = (path, Path(str(path) + '.window.json'))
                for staged in staged_files:
                    require(staged.is_file() and not staged.is_symlink(), 'regular_original_capture_required')
                    require(not (output / staged.name).exists(), 'review_media_overwrite_refused')
                for staged in staged_files:
                    target = output / staged.name
                    target.write_bytes(staged.read_bytes()); target.chmod(0o600)
                report['media'] = {'file': path.name, 'sha256': sha(path.read_bytes())}
                report['media_exportable'] = True
            cleanup('privacy_and_media_export', publish_guarded_media)
        report['acquisition_wall_seconds'] = time.monotonic() - started
        target = output / (appearance + '-motion.json')
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    require(report['status'] == 'CAPTURED_TECHNICAL_ONLY', 'motion_acquisition_or_cleanup_failed')
    return report
