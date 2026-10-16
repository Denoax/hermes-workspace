"""Explicitly gated no-model interaction acceptance through the actual Hermes pin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import traceback
import uuid

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SOURCES = ('scripts/production_pin.py', 'scripts/owned_v6_interactions.py', 'scripts/probe_v6_interactions.py',
           'scripts/probe_v4_visual.py', 'scripts/probe_v4_chat.py', 'scripts/probe_v4_uploads.py',
           'scripts/probe_v5_owned_actions.py', 'scripts/settled_overlay.py',
           'workspace/server.py', 'workspace/launcher.py', 'workspace/catalog.py',
           'workspace/reset.py', 'workspace/attachments.py', 'workspace/frontend/src/main.tsx',
           'workspace/frontend/src/controls.tsx', 'workspace/frontend/src/AnchoredPopover.tsx',
           'workspace/frontend/src/lib/composing-intent.ts', 'workspace/frontend/src/lib/conversation-management.ts',
           'workspace/frontend/src/lib/workspace-surface.ts', 'workspace/frontend/src/style.css',
           'workspace/frontend/src/interaction-surfaces.css', 'workspace/ui/dist/identities.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-recovery', type=Path, required=True,
                        help='Owner-only directory under private-state; raw original presentation stays outside review output.')
    parser.add_argument('--resume-owned-case', type=Path,
                        help='Resume only Q/D/E from an exact restored prior receipt with completed A/New/B checks; creates no new records.')
    parser.add_argument('--execute-production-probe', action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe:
        parser.error('explicit actual-production execution flag required')
    if os.getuid() == 0:
        parser.error('normal unprivileged operator required')
    root = args.app_root.resolve(strict=True)
    sys.path.insert(0, str(root))
    from scripts.owned_v6_interactions import OwnedInteractions, check
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import prepare, native_pointer_check, enable_native_input, close_panels
    from scripts.probe_v5_owned_actions import cleanup_steps, runtime_identity
    from workspace.server import normal_profile_unchanged

    output = args.output
    check(not any(p.is_symlink() for p in (output, *output.parents)), 'output_symlink_refused')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    check(output.stat().st_uid == os.getuid() and not output.stat().st_mode & 0o077, 'private_output_required')
    target = output/'run.json'
    check(not target.exists(), 'previous_attempt_must_be_preserved')
    source_before = {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES}
    report = {'status':'IN_PROGRESS', 'scope':'actual pin18791; no inference, new positively owned metadata/draft/upload records only',
              'source_sha256_before':source_before, 'native_pointer':[], 'cleanup':{},
              'remaining':['No model/guest/device/listening or human motion approval is claimed by this helper.']}
    def save():
        target.write_text(json.dumps(report, indent=2)+'\n')
        target.chmod(0o600)
    browser = review = None
    cursor = None
    restored = False
    phase = 'startup'
    save()
    def alarm(_signal, _frame):
        raise TimeoutError('interaction_acceptance_600_second_deadline')
    previous = signal.signal(signal.SIGALRM, alarm)
    previous_term = signal.signal(signal.SIGTERM, alarm)
    signal.alarm(600)
    try:
        check(normal_profile_unchanged(), 'normal_profile_changed_before_probe')
        browser = ProductionPin()
        # Do not reload before checking whether somebody typed into the fresh pin.
        browser.wait("!!document.querySelector('#prompt')&&!document.querySelector('#prompt').disabled")
        report['runtime_before'] = runtime_identity(browser, root)
        review = OwnedInteractions(browser, rpc, output/'owned', args.private_recovery)
        if args.resume_owned_case:
            phase = 'guard_existing_owned_case'
            existing_text = review.adopt_existing(args.resume_owned_case)
        else:
            review.create()
        review.select_a()
        def qualify(stage):
            nonlocal cursor
            native = getattr(browser, '_native_input', None)
            if native:
                native.close()
            browser._native_input = None
            close_panels(browser)
            prepare(browser)
            proof = native_pointer_check(browser)
            report['native_pointer'].append({'stage':stage, **proof})
            save()
            check(proof['status'] == 'PASS', 'native_pointer_not_qualified')
            if cursor is None:
                cursor = browser._native_initial_cursor
            enable_native_input(browser)
        if args.resume_owned_case:
            phase = 'existing_A_rehydrate'
            qualify(phase)
            review.baseline_existing_a(existing_text)
            phase = 'unselected_Q_folder_management'
            review.folder_management()
        else:
            phase = 'prepare_owned_A'
            qualify(phase)
            review.prepare_a()
            phase = 'new_conversation_reload_and_breadcrumb'
            review.composing(qualify)
            phase = 'explicit_row_target_management'
            review.management()
        phase = 'known_empty_D_deletion'
        review.deletion()
        phase = 'owned_empty_E_stale_target'
        review.stale_target()
        report['runtime_after'] = runtime_identity(browser, root)
        check(report['runtime_after'] == report['runtime_before'], 'production_runtime_changed_during_probe')
        report['sequence_completed'] = True
    except Exception as error:
        private_trace = traceback.format_exc()
        detail = str(error)
        report.update(phase=phase, error_category=type(error).__name__,
                      error_code=detail if re.fullmatch('[a-zA-Z][a-zA-Z0-9_]{0,179}', detail) else 'observer_or_application_error')
        if review:
            report['owned_phase'] = review.report.get('phase')
            try:
                directory = args.private_recovery
                check('private-state' in directory.parts and not any(p.is_symlink() for p in (directory, *directory.parents))
                      and directory.stat().st_uid == os.getuid() and not directory.stat().st_mode & 0o077,
                      'private_trace_directory_required')
                name = 'interaction-failure-' + uuid.uuid4().hex + '.json'
                payload = {'phase':phase, 'owned_phase':report['owned_phase'], 'traceback':private_trace}
                if browser:
                    try:
                        payload['ui'] = browser.evaluate("({focused:document.activeElement?.tagName,focused_id:document.activeElement?.id,"
                            "dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>({title:d.querySelector('h2')?.textContent,rect:d.getBoundingClientRect().toJSON(),"
                            "input_count:d.querySelectorAll('input').length})),last_pointer:globalThis.__v4pointer,"
                            "last_activations:globalThis.__v4input?.slice(-5)})")
                    except Exception as diagnostic_error:
                        payload['ui_error_category'] = type(diagnostic_error).__name__
                fd = os.open(directory/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(payload, stream, indent=2)
                report['private_failure_diagnostic'] = name
            except Exception as trace_error:
                report['private_trace_error_category'] = type(trace_error).__name__
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        signal.signal(signal.SIGTERM, previous_term)
        def restore():
            nonlocal restored
            review.restore()
            restored = True
        def close_native():
            native = getattr(browser, '_native_input', None)
            if native:
                native.close()
            browser._native_input = None
        def restore_cursor():
            if cursor:
                subprocess.run(['/usr/bin/hyprctl','dispatch','hl.dsp.cursor.move({x='+str(round(cursor['x']))+',y='+str(round(cursor['y']))+'})'],
                               capture_output=True, check=True, timeout=4)
        def close_pin():
            if not restored:
                browser.detach_preserving_document()
            else:
                browser.close()
        steps = []
        if review:
            steps.append(('original_presentation', restore))
            steps.append(('owned_upload_fixture', review.cleanup_fixture))
        if browser:
            steps.extend([('native_input', close_native), ('cursor', restore_cursor), ('pin', close_pin)])
        steps.append(('normal_configuration', lambda:check(normal_profile_unchanged(), 'normal_profile_changed_after_probe')))
        report['cleanup'] = cleanup_steps(steps)
        try:
            source_after = {p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in SOURCES}
            report['source_sha256_after'] = source_after
            report['source_unchanged'] = source_after == source_before
        except Exception as error:
            report['source_unchanged'] = False
            report['source_verification_error_category'] = type(error).__name__
        if review:
            report['owned_case_report'] = 'owned/interactions.json'
            review.report['status'] = 'PASS_SCOPED_TECHNICAL' if report.get('sequence_completed') and restored else 'PARTIAL'
            review.save()
        report['status'] = 'PASS_SCOPED_TECHNICAL' if report.get('sequence_completed') and report['source_unchanged'] and all(
            row['status'] == 'ok' for row in report['cleanup'].values()) else 'FAIL'
        save()
    print(json.dumps({'status':report['status'], 'report':str(target)}), flush=True)
    if report['status'] != 'PASS_SCOPED_TECHNICAL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
