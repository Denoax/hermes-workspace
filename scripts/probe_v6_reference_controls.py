"""One owned-A R01 or R02 native diagnostic; no inference or data edits.

Read/apply $reference-led-design. Invoke only after native authentication ends.
R05 remains the separate exact-historical-receipt reuse recipe, not this probe.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import time

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SOURCES = ('scripts/production_pin.py', 'scripts/owned_v6_interactions.py', 'scripts/probe_v6_geometry.py',
    'scripts/v6_surface_review.py', 'scripts/v6_motion_review.py', 'scripts/v6_zoom_restore.py',
    'scripts/v6_preferences_review.py', 'scripts/probe_v6_import.py', 'scripts/probe_v4_visual.py', 'scripts/probe_v4_chat.py',
    'scripts/probe_local_chat.py', 'scripts/probe_v5_shell.py', 'scripts/probe_v5_owned_actions.py',
    'workspace/parity_browser.py', 'workspace/native_coordinates.py','workspace/capture.py', 'workspace/launcher.py', 'workspace/server.py',
    'workspace/frontend/src/main.tsx', 'workspace/frontend/src/controls.tsx',
    'workspace/frontend/src/AnchoredPopover.tsx', 'workspace/frontend/src/style.css',
    'workspace/frontend/src/interaction-surfaces.css', 'workspace/ui/interface-audio.mjs',
    'workspace/ui/dist/identities.json', 'workspace/ui/dist/app.js', 'workspace/ui/dist/app.css')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('r01', 'r02'), required=True)
    p.add_argument('--app-root', type=Path, default=ROOT)
    p.add_argument('--owned-case', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--private-recovery', type=Path, required=True)
    p.add_argument('--record', action='store_true', help='Silent unedited app-XID clip with existing24s watchdog/30s recorder cap.')
    p.add_argument('--execute-production-probe', action='store_true')
    args = p.parse_args()
    if not args.execute_production_probe or os.getuid() == 0:
        p.error('explicit opt-in and normal unprivileged operator required')
    root = args.app_root.resolve(strict=True); sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.owned_v6_interactions import OwnedInteractions, owned_row
    from scripts.probe_v6_geometry import load_case, surface_case
    from scripts.v6_surface_review import SurfaceReview, require_owned_native_focus, viewport
    from scripts.v6_motion_review import attachment_proof, verify_aggregate_bytes, privacy_guard, ClipWatchdog
    from scripts.v6_preferences_review import media_state
    from scripts.v6_zoom_restore import active_owned, qualify_points_once, command
    from scripts.probe_v6_import import setup_base_window, owned_base_window
    from scripts.probe_v4_visual import NativeX11Input, prepare, enable_native_input, move, pointer_state
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v5_owned_actions import runtime_identity
    from workspace.capture import NativeWindowRecording
    from workspace.server import normal_profile_unchanged

    path = args.owned_case
    require(not any(x.is_symlink() for x in (path, *path.parents)) and path.is_file()
            and path.stat().st_uid == os.getuid() and path.stat().st_size <= 1024 * 1024, 'bounded_original_owned_receipt_required')
    receipt = json.loads(path.read_text()); case = load_case(receipt); proof = attachment_proof(receipt)
    require(receipt.get('kind') == 'actual_interaction_subcheck_aggregate', 'original_actual_aggregate_required')
    aggregate = verify_aggregate_bytes(receipt, path)
    out = args.output
    require('private-state' in out.parts and not any(x.is_symlink() for x in (out, *out.parents)), 'new_private_output_required')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    require(out.stat().st_uid == os.getuid() and not out.stat().st_mode & 0o077, 'operator_only_output_required')
    source_before = {name: sha(root / name) for name in SOURCES}
    report = {'status': 'IN_PROGRESS', 'mode': args.mode,
        'scope': 'ONE actual existing pin18791 and exact original harmless owned A. No model, chooser, new record, upload, metadata edit, deletion, policy/audio-setting change, fake state or link navigation.',
        'case_receipt_sha256': sha(path), 'aggregate_original_identity': aggregate,
        'source_sha256_before': source_before, 'diagnostic_sha256': sha(Path(__file__)),
        'checks': {}, 'native_qualification': [], 'cleanup': {}, 'media_exportable': False,
        'reference_parity_and_human_continuous_motion_approval': 'UNVERIFIED',
        'physical_input_listening_GPU_or_presentation_timing': 'UNVERIFIED'}
    target = out / (args.mode + '.json')
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    browser = owner = surface = recorder = watchdog = None
    cursor = address = native_surface = original_effort = a_effort = preferences = original_prompt_model = None
    original_appearance = expected_A_view = base_window_identity = None
    observed = False
    presentation_staged = False
    def guard_roles():
        for role in ('A', 'B', 'P', 'Q'):
            owned_row(case, role, rpc(browser, 'session.list' if role in ('A', 'B') else 'workspace.list', {}))
    def qualify():
        nonlocal cursor, address, native_surface
        require(base_window_identity is not None, 'once_only_base_setup_required_before_qualification')
        _, before = owned_base_window(launcher, expected=base_window_identity)
        require(before['fully_inside_monitor'], 'base_window_outside_before_reference_qualification')
        client = active_owned(browser, address); address = client['address']
        require({'address': client['address'], 'pid': client['pid']} == base_window_identity,
                'same_setup_and_active_native_window_required')
        if cursor is None: cursor = command('/usr/bin/hyprctl', 'cursorpos', '-j')
        require(getattr(browser, '_native_input', None) is None, 'no_old_native_mapping_required')
        browser._native_input = NativeX11Input()
        result = qualify_points_once(browser, browser._native_input, client)
        report['native_qualification'].append(result); save()
        require(result['status'] == 'PASS_POINTS_ONLY', 'fresh_no_focus_force_native_points_required')
        _, after = owned_base_window(launcher, expected=base_window_identity)
        report['base_window_qualification'] = {'before': before, 'after': after}; save()
        require(after['fully_inside_monitor'], 'base_window_outside_after_reference_qualification')
        require((after['position'], after['size']) == (client['at'], client['size']),
                'base_window_moved_during_reference_qualification')
        browser._native_coordinates = (*result['mapping'], address)
        browser._native_diagnostics = {'status': 'PASS', 'scope': 'One13-point native pass, no Settings click or focus forcing.'}
        native_surface = (client['at'], client['size']); enable_native_input(browser)
        return {'status': 'PASS', 'point_observation': result}
    def guarded_native():
        guard_roles(); owner.assert_a(); surface._guard(); require_owned_native_focus(browser)
        require(expected_A_view is None or owner.rpc('view.read') == expected_A_view, 'newer_A_view_preference_preserved')
        client = active_owned(browser, address)
        require((client['at'], client['size']) == native_surface, 'native_surface_drift_abort_without_refocus')
    def thinking():
        return browser.evaluate('document.querySelector("#effort-toggle .brain-icon").classList.contains("brain-on")')
    def restore_a_effort():
        if a_effort is None: return
        guarded_native()
        if thinking() != a_effort:
            if not browser.evaluate('!!document.querySelector("#reasoning-effort")'):
                surface.click('#effort-toggle'); browser.wait('!!document.querySelector("#reasoning-effort")')
            surface.click('#reasoning-effort'); surface.key('Right' if a_effort else 'Left')
            browser.wait('document.querySelector("#reasoning-effort").value===' + json.dumps('1' if a_effort else '0'))
        require(thinking() == a_effort, 'original_transient_A_effort_not_restored')
        surface.close()
    def hold(seconds):
        if recorder: recorder.hold(seconds)
        else: time.sleep(seconds)
    def alarm(_signal, _frame):
        raise TimeoutError('reference_diagnostic_bounded_deadline')
    previous = signal.signal(signal.SIGALRM, alarm); previous_term = signal.signal(signal.SIGTERM, alarm)
    signal.alarm(180); save()
    try:
        require(normal_profile_unchanged(), 'normal_configuration_changed_before_reference')
        browser = ProductionPin(); browser.wait("!!document.querySelector('#prompt')&&!document.querySelector('#prompt').disabled")
        report['runtime_before'] = runtime_identity(browser, root)
        require(not browser.evaluate('!!document.querySelector("dialog[open],.anchored-popover")'), 'original_open_surface_preserved_no_probe')
        preferences = media_state(browser); original_effort = thinking()
        require(original_effort is False, 'original_transient_thinking_on_preserved_no_probe')
        original_appearance = browser.evaluate('({theme:document.documentElement.dataset.theme,motion:document.documentElement.dataset.motion})')
        original_prompt_model = browser.evaluate('({prompt:document.querySelector("#prompt").value,model:document.querySelector("#model-picker").value,scroll:document.querySelector(".conversation").scrollTop})')
        owner = OwnedInteractions(browser, rpc, out / 'private-owner', args.private_recovery)
        guard_roles(); owner.case = deepcopy(case); owner.report['case'] = owner.case
        owner.report['scope'] = 'Reused actual A/B/P/Q reference controls; never recreate/guard deleted D/E.'; owner.save()
        a, project = case['records']['A'], case['records']['P']
        require(thinking() is False, 'original_transient_thinking_changed_preserved_no_switch')
        presentation_staged = True
        rpc(browser, 'view.write', {'state': {**owner.original_view, 'session_id': a['id'], 'project_id': project['id'], 'arm': 'normal'}})
        owner.reload(); prepare(browser)
        from workspace import launcher
        require(launcher.focus(), 'existing_pin_activation_failed')
        report['initial_activation'] = 'Existing launcher.focus routine; subsequent point qualification and input refuse displaced focus without refocusing.'
        require('base_window_setup' not in report, 'base_window_setup_must_be_once')
        report['base_window_setup'] = {}
        try:
            base_window_identity = setup_base_window(browser, launcher, report['base_window_setup'])
        finally:
            save()
        report['base_window_setup_scope'] = 'Controlled owned-app geometry before qualification or recording; this is not launcher placement acceptance.'
        surface = SurfaceReview(browser, case=surface_case(case), rpc_read=owner.rpc, requalify=qualify)
        surface.fresh_native(); guarded = lambda: (guard_roles(), require_owned_native_focus(browser))
        guarded(); owner.filter_owned()
        draft = owner.rpc('draft.read', {'session_id': a['id']})
        require(hashlib.sha256(draft['text'].encode()).hexdigest() == proof['draft_sha256'], 'later_A_draft_preserved')
        owner.baseline_existing_a(draft['text']); report['privacy_before'] = privacy_guard(owner, receipt)
        expected_A_view = owner.rpc('view.read')
        a_effort = thinking(); report['initial_transient_effort_on'] = a_effort
        report['effective_preferences'] = media_state(browser); report['viewport'] = viewport(browser)
        if args.record:
            recorder = NativeWindowRecording(browser, out / (args.mode + '-native-unedited.mp4'))
            watchdog = ClipWatchdog(recorder.process); watchdog.start()
        if args.mode == 'r01':
            surface.click('#effort-toggle'); browser.wait('!!document.querySelector("#reasoning-effort")'); surface.settle()
            slider = browser.evaluate('(()=>{const e=document.querySelector("#reasoning-effort");return {min:e.min,max:e.max,step:e.step,disabled:e.disabled}})()')
            require(not slider['disabled'] and (slider['min'], slider['max'], slider['step']) == ('0', '1', '1'), 'exact_supported_two_state_range_required')
            surface.click('#reasoning-effort'); surface.key('Left'); surface.key('Left')
            browser.wait('document.querySelector("#reasoning-effort").value==="0"'); hold(.45)
            report['checks']['off_keyboard_lower_bound'] = {'status': 'PASS', 'value': '0'}; save()
            surface.key('Right'); surface.key('Right')
            browser.wait('document.querySelector("#reasoning-effort").value==="1"'); hold(.5)
            on = browser.evaluate('({lobes:+getComputedStyle(document.querySelector(".effort-popover .brain-lobes")).opacity,thumb:document.querySelector(".brain-thumb").getBoundingClientRect().toJSON(),track:document.querySelector(".effort-track").getBoundingClientRect().toJSON(),pixel_field:!!document.querySelector(".effort-field rect"),aria:document.querySelector("#reasoning-effort").getAttribute("aria-valuetext")})')
            require(on['lobes'] > 0 and on['pixel_field'] and on['aria'] == 'Thinking on', 'actual_on_brain_pixel_field_or_semantics_missing')
            report['checks']['on_keyboard_upper_bound'] = {'status': 'PASS', 'value': '1', 'observed': on}; save()
            rect = browser.rect('#reasoning-effort'); x0, x1, y = rect['x'] + rect['width'] * .1, rect['x'] + rect['width'] * .9, rect['y'] + rect['height'] / 2
            guarded_native(); pointer_state(browser, x1, y, True)
            try:
                for index in range(5):
                    guarded_native(); move(browser, x1 + (x0 - x1) * index / 4, y)
            finally:
                browser._native_input.button(False)
            browser.wait('document.querySelector("#reasoning-effort").value==="0"'); hold(.45)
            report['checks']['native_drag_to_off'] = {'status': 'PASS', 'samples': 5, 'value': '0'}; save()
            restore_a_effort()
        else:
            require(browser.evaluate('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="false"'), 'plus_menu_must_start_closed')
            rect = browser.rect('#plus-menu'); x, y = rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2
            def metal():
                return browser.evaluate('({face:getComputedStyle(document.querySelector(".metal-face")).transform,active:document.querySelector("#plus-menu").matches(":active"),rim:[...document.querySelectorAll(".metal-rim i")].map(e=>({transform:getComputedStyle(e).transform,animations:e.getAnimations().map(a=>({time:a.currentTime,state:a.playState}))})),rect:document.querySelector("#plus-menu").getBoundingClientRect().toJSON()})')
            guarded_native(); move(browser, x, y); hold(.55); first = metal(); hold(.5); second = metal()
            limited = browser.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches||matchMedia("(forced-colors: active)").matches||document.documentElement.dataset.motion==="reduced"')
            require(first['face'] == second['face'] == 'none', 'metal_face_not_upright')
            if not limited: require(first['rim'] != second['rim'], 'actual_rim_motion_missing_with_full_motion_preferences')
            report['checks']['rim_and_fixed_face'] = {'status': 'UNAVAILABLE_BY_ORIGINAL_PREFERENCE' if limited else 'PASS', 'first': first, 'second': second}; save()
            guarded_native(); pointer_state(browser, x, y, True)
            try:
                hold(.16); guarded_native(); report['pressed_readback'] = metal()
                require(report['pressed_readback']['active'] and report['pressed_readback']['face'] == 'none', 'native_press_or_upright_face_not_observed')
            finally: browser._native_input.button(False)
            browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="true"')
            surface.key('Escape'); browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="false"')
            surface.click('#plus-menu'); browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="true"')
            surface.click('#plus-menu')
            browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="false"'); hold(.6)
            report['checks']['native_press_Escape_open_close_reversal'] = {'status': 'PASS', 'final_expanded': False}; save()
        owner.assert_a(); report['privacy_after'] = privacy_guard(owner, receipt)
        require(media_state(browser) == report['effective_preferences'], 'mode_changed_effective_preferences')
        if recorder:
            watchdog.close(); report['recorder_watchdog_fired'] = watchdog.fired; watchdog = None
            report['recording'] = recorder.finish(); recorder = None
            require(not report['recorder_watchdog_fired'] and 0 < report['recording']['seconds'] < 30, 'unedited_recording_budget_not_proven')
            report['media'] = {'file': args.mode + '-native-unedited.mp4', 'sha256': sha(out / (args.mode + '-native-unedited.mp4'))}
        report['runtime_after'] = runtime_identity(browser, root)
        require(report['runtime_after'] == report['runtime_before'], 'production_runtime_changed_during_reference')
        observed = True
        report['status'] = 'PARTIAL_SCOPED_TECHNICAL' if args.mode == 'r02' and limited else 'PASS_SCOPED_TECHNICAL'
    except Exception as error:
        code = str(error); report.update(status='FAIL', error_category=type(error).__name__,
            error_code=code if re.fullmatch('[A-Za-z0-9_]{1,180}', code) else 'reference_observer_or_application_error')
    finally:
        cleanup_until = time.monotonic() + 60
        def cleanup(name, callback):
            remaining = cleanup_until - time.monotonic()
            if remaining <= 0:
                report['cleanup'][name] = {'status': 'failed', 'error_category': 'CleanupBudgetExhausted'}; report['status'] = 'FAIL'; save(); return
            signal.alarm(max(1, math.ceil(remaining)))
            try: callback(); report['cleanup'][name] = {'status': 'ok'}
            except Exception as error: report['cleanup'][name] = {'status': 'failed', 'error_category': type(error).__name__}; report['status'] = 'FAIL'
            save()
        if browser and getattr(browser, '_native_input', None) and browser._native_input.pressed:
            cleanup('own_native_press', lambda: browser._native_input.button(False))
        if watchdog: cleanup('recorder_watchdog', watchdog.close)
        if recorder:
            cleanup('private_partial_recording', lambda: report.update(private_partial_recording=recorder.finish()))
        if surface: cleanup('A_transient_effort', restore_a_effort)
        if owner and presentation_staged:
            def restore_original():
                current = owner.rpc('view.read')
                require(expected_A_view is None or current in (expected_A_view, owner.original_view), 'newer_view_preference_preserved_no_restore')
                owner.restore()
            cleanup('original_presentation', restore_original)
            def original_ui():
                current = browser.evaluate('({prompt:document.querySelector("#prompt").value,model:document.querySelector("#model-picker").value,scroll:document.querySelector(".conversation").scrollTop})')
                require(all(current[k] == original_prompt_model[k] for k in ('prompt', 'model'))
                    and abs(current['scroll'] - original_prompt_model['scroll']) <= 1 and thinking() == original_effort,
                    'original_prompt_model_reading_or_transient_effort_not_restored')
                require(media_state(browser) == preferences, 'original_effective_preferences_not_restored')
                require(browser.evaluate('({theme:document.documentElement.dataset.theme,motion:document.documentElement.dataset.motion})') == original_appearance,
                        'original_theme_or_motion_presentation_not_restored')
            cleanup('original_prompt_model_reading_effort_preferences', original_ui)
        if browser:
            if getattr(browser, '_native_input', None): cleanup('own_native_connection', browser._native_input.close)
            if cursor:
                def restore_cursor():
                    active_owned(browser, address); connection = NativeX11Input()
                    try: connection.move(cursor['x'], cursor['y'])
                    finally: connection.close()
                cleanup('cursor', restore_cursor)
            cleanup('owned_pin', browser.close)
        cleanup('normal_configuration', lambda: require(normal_profile_unchanged(), 'normal_configuration_changed_after_reference'))
        def unchanged_sources():
            report['source_sha256_after'] = {name: sha(root / name) for name in SOURCES}
            report['source_unchanged'] = report['source_sha256_after'] == source_before
            require(report['source_unchanged'] and sha(Path(__file__)) == report['diagnostic_sha256'], 'diagnostic_sources_changed')
        cleanup('source_identity', unchanged_sources)
        report['media_exportable'] = bool(observed and args.record and report['status'] != 'FAIL')
        signal.alarm(0); signal.signal(signal.SIGALRM, previous); signal.signal(signal.SIGTERM, previous_term); save()
    return 0 if report['status'] in ('PASS_SCOPED_TECHNICAL', 'PARTIAL_SCOPED_TECHNICAL') else 2


if __name__ == '__main__':
    raise SystemExit(main())
