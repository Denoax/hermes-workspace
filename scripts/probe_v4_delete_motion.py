"""Record real conversation delete confirmation and cancellation; never delete.

The case JSON must identify the completed, nonce-labelled final-sequence normal
conversation. Uses the actual production pin/profile/catalog on 18791 and the
already verified native input/window capture helpers. No fixtures or fetch
replacement, inference, confirmed deletion, audio capture, or new records.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from scripts.probe_v4_visual import (
    check, close_panels, enable_native_input, input_text,
    native_pointer_check, prepare, reduced_motion, rpc as raw_rpc, shot,
)
from workspace.capture import NativeWindowRecording


def rpc(browser, method, fields=None):
    # A 429 is rejected before dispatch. Retry that explicit admission response
    # only, at most twice, without increasing the production rate limit.
    for attempt in range(3):
        try:
            return raw_rpc(browser, method, fields)
        except RuntimeError as error:
            if 'rate_limit' not in str(error) or attempt == 2:
                raise
            browser._delete_rate_retries = getattr(browser, '_delete_rate_retries', 0) + 1
            browser.evaluate('new Promise(resolve=>setTimeout(resolve,1100))')


def metadata_fingerprint(browser):
    rows = {method: rpc(browser, method) for method in ('workspace.list', 'session.list')}
    return digest(rows), {method: len(value) for method, value in rows.items()}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def owned_case(path):
    case = json.loads(path.read_text())
    check(case.get('status') == 'PASS' and case.get('arm') == 'normal', 'completed_normal_case_required')
    session_id = case.get('session_id', '')
    nonce = case.get('verification_word', '')
    check(bool(re.fullmatch(r'[a-f0-9]{32}', session_id)), 'invalid_owned_case_session')
    check(bool(re.fullmatch(r'maple-[a-f0-9]{8}', nonce)), 'invalid_owned_case_nonce')
    check(case.get('capture_navigation_filter') == nonce, 'owned_case_filter_mismatch')
    prompts = case.get('test_prompts')
    check(isinstance(prompts, list) and prompts and all(nonce in prompt for prompt in prompts), 'owned_case_prompts_not_identified')
    return session_id, nonce


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--case', type=Path, required=True)
    args = parser.parse_args()
    session_id, nonce = owned_case(args.case)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {
        'status': 'IN_PROGRESS', 'scope': 'actual Hermes pin / production catalog / 127.0.0.1:18791',
        'case': str(args.case), 'case_sha256': hashlib.sha256(args.case.read_bytes()).hexdigest(),
        'session_id': session_id, 'navigation_filter': nonce, 'fixtures': False,
        'model_inference_started': False, 'new_records_created': False,
        'human_visual_approval': 'PENDING', 'continuous_human_motion_approval': 'PENDING',
        'captures': [], 'checks': {}, 'RPC_method_counts': {},
    }
    browser = recording = None
    initial_view = storage = before_metadata = before_history = None
    prior_callback = None
    observed_methods = []
    try:
        browser = ProductionPin()
        prepare(browser)
        browser.evaluate('new Promise(resolve=>setTimeout(resolve,1100))')
        report['pin'] = browser.identity
        report['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                  for name in ('scripts/probe_v4_delete_motion.py', 'scripts/probe_v4_visual.py',
                                               'scripts/production_pin.py', 'workspace/capture.py', 'workspace/launcher.py',
                                               'workspace/frontend/src/components/delete-button.tsx')}
        report['served_app_js_sha256'] = browser.evaluate("fetch('/assets/app.js',{cache:'no-store'}).then(r=>r.arrayBuffer()).then(b=>crypto.subtle.digest('SHA-256',b)).then(h=>Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join(''))")
        check(report['served_app_js_sha256'] == hashlib.sha256((ROOT/'workspace/ui/dist/app.js').read_bytes()).hexdigest(), 'served_candidate_asset_mismatch')
        initial_view = rpc(browser, 'view.read')
        before_metadata, _counts = metadata_fingerprint(browser)
        rows = rpc(browser, 'session.list')
        selected = next((row for row in rows if row['id'] == session_id), None)
        check(selected and selected['arm'] == 'normal' and nonce in selected['title'], 'actual_case_session_ownership_not_proven')
        before_history = digest(rpc(browser, 'session.history', {'session_id': session_id}))
        storage = browser.evaluate("Object.fromEntries(['hermes-ui:sounds'].map(key=>[key,localStorage.getItem(key)]))")
        prior_callback = browser.pipe.on_event

        def observe(message):
            if message.get('method') == 'Network.requestWillBeSent':
                request = message.get('params', {}).get('request', {})
                if request.get('url', '').endswith('/hermes-workspace/api/rpc') and request.get('postData'):
                    try:
                        method = json.loads(request['postData']).get('method')
                    except (ValueError, AttributeError):
                        method = None
                    if isinstance(method, str) and re.fullmatch(r'[a-z_.]+', method):
                        observed_methods.append(method)
            if prior_callback:
                prior_callback(message)
        browser.pipe.on_event = observe
        browser.call('Network.enable')
        close_panels(browser)
        browser.click('.all-conversations')
        input_text(browser, '.rail-search input', nonce)
        browser.wait("document.querySelectorAll('.session-row').length===1 && [...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')].every(e=>e.textContent.includes(" + json.dumps(nonce) + "))")
        browser.click('.session-row>button:first-child')
        browser.wait("document.querySelector('.session-row.selected>button')?.textContent.includes(" + json.dumps(nonce) + ")")
        check(digest(rpc(browser, 'session.history', {'session_id': session_id})) == before_history, 'history_changed_before_probe')
        if browser.evaluate("document.querySelector('#sound-toggle').dataset.sound==='on'"):
            browser.click('#sound-toggle')
        reduced_motion(browser, False)
        report['native_pointer'] = native_pointer_check(browser)
        check(report['native_pointer']['status'] == 'PASS', 'native_pointer_not_qualified')
        enable_native_input(browser)
        report['input'] = 'Paired compositor warp and native XTEST X11 server events; trusted DOM/compositor readbacks verified. Not physical user input.'
        recording = NativeWindowRecording(browser, output/'delete-cancel-unedited.mp4')
        recording.hold(.35)
        browser.click('.session-row.selected .session-options')
        browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Conversation'")
        delete = 'dialog[open] [data-slot="delete-button"]'
        trigger = delete + ' button[aria-label="Delete"]'
        browser.wait("document.querySelector('dialog[open] [data-slot=\"delete-button\"]')?.dataset.state==='closed'")
        report['mount_width'] = browser.rect(delete)['width']
        report['inline_initial_width'] = browser.evaluate("document.querySelector('dialog[open] [data-slot=\"delete-button\"]').style.width")
        check(44 <= report['mount_width'] <= 49 and report['inline_initial_width'] == '48px', 'delete_initial_width_flash_regression')
        report['checks']['initial_tile_width_preserved'] = True
        # Retain the complete entry in the unedited video; measure the idle
        # baseline only once its finite mount animation has reached rest.
        browser.wait("Math.abs(document.querySelector('dialog[open] [data-slot=\"delete-button\"]').getBoundingClientRect().width-48)<.5")
        recording.hold(.2)
        report['idle_width'] = browser.rect(delete)['width']
        browser.click(trigger)
        browser.wait("document.querySelector('dialog[open] [data-slot=\"delete-button\"]')?.dataset.state==='open'")
        recording.hold(.8)
        report['open_width'] = browser.rect(delete)['width']
        check(report['open_width'] >= 130 and report['idle_width'] <= 49, 'delete_confirmation_geometry_not_expanded')
        shot(browser, output, 'delete-confirm-open', report['captures'])
        browser.click(delete + ' button[aria-label="Cancel"]')
        browser.wait("document.querySelector('dialog[open] [data-slot=\"delete-button\"]')?.dataset.status==='kept'")
        report['checks']['Cancel_returns_kept'] = True
        recording.hold(.85)
        check(browser.rect(delete)['width'] <= 49, 'cancel_did_not_collapse_confirmation')
        shot(browser, output, 'delete-cancelled', report['captures'])
        check(digest(rpc(browser, 'session.history', {'session_id': session_id})) == before_history, 'Cancel_changed_history')
        browser.click(trigger)
        browser.wait("document.querySelector('dialog[open] [data-slot=\"delete-button\"]')?.dataset.state==='open'")
        recording.hold(.75)
        browser.key('Escape')
        browser.wait("!document.querySelector('dialog[open] [data-slot=\"delete-button\"][data-state=\"open\"]')")
        recording.hold(.75)
        report['Escape_result'] = browser.evaluate("document.querySelector('dialog[open]')?'confirmation collapsed within panel':'Conversation panel closed'")
        report['checks']['Escape_exits_confirmation'] = True
        check(digest(rpc(browser, 'session.history', {'session_id': session_id})) == before_history, 'Escape_changed_history')
        report['checks']['history_preserved_after_Cancel_and_Escape'] = True
        recording.hold(.35)
        finished, recording = recording, None
        report['recording'] = finished.finish()
        report['checks']['no_content_delete_RPC_observed'] = 'content.delete' not in observed_methods
        check(report['checks']['no_content_delete_RPC_observed'], 'unexpected_content_delete_RPC')
        report['status'] = 'PASS scoped technical checks'
    except Exception as error:
        report.update(status='FAIL', error=str(error)[:400] or type(error).__name__)
    finally:
        if recording:
            try:
                report['partial_recording'] = recording.finish()
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                report['recording_error'] = str(error)[:200]
        if browser:
            try:
                close_panels(browser)
                if initial_view:
                    reduced_motion(browser, initial_view.get('motion') == 'reduced')
                if storage:
                    enabled = storage['hermes-ui:sounds'] != 'off'
                    if browser.evaluate("document.querySelector('#sound-toggle').dataset.sound==='on'") != enabled:
                        browser.click('#sound-toggle')
                    browser.evaluate('Object.entries(' + json.dumps(storage) + ').forEach(([k,v])=>v===null?localStorage.removeItem(k):localStorage.setItem(k,v))')
                if initial_view:
                    rpc(browser, 'view.write', {'state': initial_view})
                    report['checks']['initial_view_restored'] = rpc(browser, 'view.read') == initial_view
                if before_metadata:
                    after, _counts = metadata_fingerprint(browser)
                    report['checks']['project_conversation_metadata_unchanged'] = after == before_metadata
                if before_history:
                    report['checks']['owned_history_unchanged'] = digest(rpc(browser, 'session.history', {'session_id': session_id})) == before_history
                report['checks']['no_content_delete_RPC_observed'] = 'content.delete' not in observed_methods
                report['explicit_rate_limit_retries'] = getattr(browser, '_delete_rate_retries', 0)
                for method in sorted(set(observed_methods)):
                    report['RPC_method_counts'][method] = observed_methods.count(method)
                if not all(report['checks'].values()):
                    report['status'] = 'FAIL'
            except Exception as error:
                report.update(status='FAIL', restoration_error=str(error)[:200])
            finally:
                cursor = getattr(browser, '_native_initial_cursor', None)
                if cursor:
                    subprocess.run(['/usr/bin/hyprctl', 'dispatch', f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'], capture_output=True, timeout=4)
                native = getattr(browser, '_native_input', None)
                if native:
                    native.close()
                browser.pipe.on_event = prior_callback
                browser.close()
        (output/'delete-motion.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'report': str(output/'delete-motion.json')}))
    if report['status'] != 'PASS scoped technical checks':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
