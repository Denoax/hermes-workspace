"""Capture bounded unedited native Hermes transitions on an existing owned case.

Read and apply $reference-led-design. Explicit execution flag; ONE real pin.
No models, destructive actions, chooser, new records or animation overrides.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SOURCES = ('scripts/probe_v6_motion.py', 'scripts/v6_motion_review.py', 'scripts/probe_v6_geometry.py',
           'scripts/production_pin.py', 'scripts/owned_v6_interactions.py', 'scripts/v6_surface_review.py',
           'scripts/probe_v4_visual.py', 'scripts/probe_v5_owned_actions.py', 'scripts/performance_sampler.js',
           'scripts/performance_summary.py', 'scripts/probe_v4_chat.py',
           'workspace/capture.py', 'workspace/launcher.py', 'workspace/server.py',
           'workspace/desktop.py', 'workspace/native_picker.py',
           'workspace/frontend/src/main.tsx', 'workspace/frontend/src/controls.tsx',
           'workspace/frontend/src/AnchoredPopover.tsx', 'workspace/frontend/src/lib/workspace-surface.ts',
           'workspace/frontend/src/interaction-surfaces.css', 'workspace/frontend/src/style.css',
           'workspace/frontend/src/Buddy.tsx', 'workspace/frontend/src/buddy.css',
           'workspace/ui/dist/identities.json', 'workspace/ui/sounds/click1.wav',
           'workspace/ui/sounds/mouseclick1.wav', 'workspace/ui/sounds/mouserelease1.wav',
           'workspace/ui/sounds/soft-press.wav', 'workspace/ui/sounds/soft-close.wav')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=ROOT)
    parser.add_argument('--owned-case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-recovery', type=Path, required=True)
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe or os.getuid() == 0:
        parser.error('explicit production probe flag and unprivileged operator required')
    root = args.app_root.resolve(strict=True); sys.path.insert(0, str(root))
    from scripts.probe_v6_geometry import load_case, surface_case
    from scripts.production_pin import ProductionPin
    from scripts.owned_v6_interactions import OwnedInteractions, owned_row
    from scripts.v6_surface_review import SurfaceReview, viewport
    from scripts.v6_motion_review import attachment_proof, privacy_guard, record_clip, verify_aggregate_bytes
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import prepare, native_pointer_check, enable_native_input, close_panels, theme
    from scripts.probe_v5_shell import retire_native_input
    from scripts.probe_v5_owned_actions import cleanup_steps, runtime_identity
    from workspace.server import normal_profile_unchanged

    require(not any(p.is_symlink() for p in (args.owned_case, *args.owned_case.parents))
            and args.owned_case.is_file() and args.owned_case.stat().st_size <= 1024 * 1024, 'bounded_regular_owned_receipt_required')
    receipt = json.loads(args.owned_case.read_text()); case = load_case(receipt); proof = attachment_proof(receipt)
    aggregate_bytes = verify_aggregate_bytes(receipt, args.owned_case)
    output = args.output
    require(not any(p.is_symlink() for p in (output, *output.parents)), 'output_symlink_refused')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    require(output.stat().st_uid == os.getuid() and not output.stat().st_mode & 0o077, 'owner_only_motion_output_required')
    source_before = {name: digest(root / name) for name in SOURCES}
    report = {'status': 'IN_PROGRESS', 'scope': 'ONE actual production pin18791; existing positively identified harmless A/B; no model, chooser, new records, edits, submit or deletion.',
              'case_receipt_sha256': digest(args.owned_case), 'source_sha256_before': source_before,
              'aggregate_original_receipt_identity': aggregate_bytes,
              'clips': [], 'native_qualification': [], 'cleanup': {},
              'human_visual_and_continuous_motion_approval': 'UNVERIFIED',
              'physical_input_listening_and_presentation_timing': 'UNVERIFIED',
              'remaining': ['Acquisition is not uninterrupted agent/human perceptual review or Mani approval.',
                            'No real R03/R04 model phases, guest progression, voice/device state or chooser is invented for this recording.',
                            'CPU callback metrics include active recorder/observer overhead; no controlled baseline/candidate comparison or GPU/display cadence claim.']}
    target = output / 'motion.json'
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    browser = owner = surface = None
    cursor = None
    restored = False
    def alarm(_signal, _frame):
        raise TimeoutError('motion_probe_240_second_deadline')
    previous = signal.signal(signal.SIGALRM, alarm); previous_term = signal.signal(signal.SIGTERM, alarm)
    signal.alarm(240); save()
    try:
        require(normal_profile_unchanged(), 'normal_configuration_changed_before_motion')
        browser = ProductionPin()
        browser.wait("!!document.querySelector('#prompt')&&!document.querySelector('#prompt').disabled")
        report['runtime_before'] = runtime_identity(browser, root)
        owner = OwnedInteractions(browser, rpc, output / 'preservation', args.private_recovery)
        for role in ('A', 'B', 'P', 'Q'):
            owned_row(case, role, rpc(browser, 'session.list' if role in ('A', 'B') else 'workspace.list', {}))
        owner.case = deepcopy(case); owner.report['case'] = owner.case; owner.report['scope'] = 'Reused actual owned case for native motion; no new records.'
        owner.save(); owner.select_a(); prepare(browser)
        draft = rpc(browser, 'draft.read', {'session_id': case['records']['A']['id']})
        require(hashlib.sha256(draft['text'].encode()).hexdigest() == proof['draft_sha256'], 'later_A_edit_preserved_before_motion')
        owner.baseline_existing_a(draft['text'])
        privacy_guard(owner, receipt)
        def qualify():
            nonlocal cursor
            retire_native_input(browser); close_panels(browser)
            value = native_pointer_check(browser)
            report['native_qualification'].append(value); save()
            require(value['status'] == 'PASS', 'actual_native_motion_pointer_not_qualified')
            if cursor is None:
                cursor = browser._native_initial_cursor
            enable_native_input(browser)
            return value
        def rpc_read(method, fields):
            require(method in ('view.read', 'draft.read', 'session.list'), 'read_only_surface_RPC_required')
            return rpc(browser, method, fields)
        surface = SurfaceReview(browser, case=surface_case(case), rpc_read=rpc_read, requalify=qualify)
        surface.fresh_native()
        require(viewport(browser)['visual_scale'] == 1, 'unscaled_actual_motion_viewport_required')
        private_staging = args.private_recovery / ('motion-' + case['nonce'] + '-' + output.name)
        for appearance in ('dark', 'light'):
            theme(browser, appearance)
            owner.poll(lambda: rpc(browser, 'view.read', {}).get('theme') == appearance,
                       'authenticated_view_theme_did_not_settle')
            surface.fresh_native()
            owner.assert_a()
            try:
                clip = record_clip(browser, surface, owner, receipt, root, output, private_staging, appearance)
            finally:
                artifact = output / (appearance + '-motion.json')
                if artifact.is_file():
                    report['clips'].append(json.loads(artifact.read_text())); save()
            require(clip['status'] == 'CAPTURED_TECHNICAL_ONLY' and clip['media_exportable'], 'motion_clip_not_guarded_for_review')
        report['runtime_after'] = runtime_identity(browser, root)
        require(report['runtime_after'] == report['runtime_before'], 'production_runtime_changed_during_motion')
        report['acquisition_completed'] = True
    except Exception as error:
        code = str(error)
        report.update(error_category=type(error).__name__, error_code=code if re.fullmatch('[A-Za-z0-9_:;.-]{1,256}', code) else 'observer_or_application_error')
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous); signal.signal(signal.SIGTERM, previous_term)
        def release_press():
            native = getattr(browser, '_native_input', None)
            if native and getattr(native, 'pressed', False):
                native.button(False)
        def restore():
            nonlocal restored
            owner.restore(); restored = True
        def restore_cursor():
            if cursor:
                subprocess.run(['/usr/bin/hyprctl', 'dispatch', f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'], check=True, capture_output=True, timeout=4)
        def close_pin():
            if restored:
                browser.close()
            else:
                browser.detach_preserving_document()
        steps = []
        if browser:
            steps.append(('native_press', release_press))
        if owner:
            steps.append(('original_presentation', restore))
        if browser:
            steps += [('native_input', lambda: retire_native_input(browser)), ('cursor', restore_cursor), ('owned_pin', close_pin)]
        steps.append(('normal_configuration', lambda: require(normal_profile_unchanged(), 'normal_configuration_changed_after_motion')))
        report['cleanup'] = cleanup_steps(steps)
        report['source_sha256_after'] = {name: digest(root / name) for name in SOURCES}
        report['source_unchanged'] = source_before == report['source_sha256_after']
        report['status'] = 'CAPTURED_TECHNICAL_ONLY' if report.get('acquisition_completed') and report['source_unchanged'] and all(
            item['status'] == 'ok' for item in report['cleanup'].values()) else 'FAIL'
        save()
    print(json.dumps({'status': report['status'], 'report': str(target)}), flush=True)
    if report['status'] != 'CAPTURED_TECHNICAL_ONLY':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
