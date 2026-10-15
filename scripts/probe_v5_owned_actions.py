"""Bounded actual-pin owned-action review. No production work without execute flag."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

APP_ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
BASE = Path('/home/mani/mani-hermes-v5-6of3k6oz')
SOURCES = (
    'scripts/production_pin.py', 'scripts/probe_v4_chat.py', 'scripts/probe_v4_visual.py',
    'scripts/owned_action_review.py', 'scripts/owned_native_picker.py', 'scripts/probe_v5_owned_actions.py',
    'workspace/capture.py', 'workspace/launcher.py', 'workspace/server.py',
    'workspace/actions.py', 'workspace/permissions.py', 'workspace/catalog.py',
    'workspace/files.py', 'workspace/search.py', 'workspace/attachments.py',
    'workspace/frontend/src/main.tsx', 'workspace/frontend/src/lib/draft-selection.ts',
    'workspace/frontend/src/lib/use-draft-attachments.ts',
    'workspace/frontend/src/permissions.tsx', 'workspace/frontend/src/style.css',
    'workspace/frontend/src/components/web-search.tsx',
    'workspace/frontend/src/components/folder-component.tsx',
    'workspace/frontend/src/components/delete-button.tsx',
    'workspace/ui/dist/identities.json', 'workspace/ui/dist/app.js', 'workspace/ui/dist/app.css',
)


def check(condition, code):
    if not condition:raise RuntimeError(code)


def source_snapshot(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCES}


def cleanup_steps(steps):
    """Attempt every independent resource cleanup and retain every failure."""
    results = {}
    for name, callback in steps:
        try:
            callback(); results[name] = {'status': 'ok'}
        except Exception as error:
            results[name] = {'status': 'failed', 'error_category': type(error).__name__}
    return results


class RotatingRecordings:
    def __init__(self, browser, output, receipts, save, factory, clock=time.monotonic):
        self.browser, self.output, self.receipts, self.save = browser, Path(output), receipts, save
        self.factory, self.clock = factory, clock
        self.current = None; self.number = 0

    def segment(self, name):
        check(bool(re.fullmatch('[a-z][a-z0-9_]{0,70}', name)), 'fixed_recording_segment_name_required')
        self.finish(); self.number += 1
        self.name = f'{self.number:02d}-{name}-unedited.mp4'
        self.started = self.clock()
        self.current = self.factory(self.browser, self.output / self.name)

    def hold(self, seconds):
        check(self.current is not None and 0 <= seconds <= 3, 'bounded_active_recording_required')
        check(self.clock() - self.started + seconds < 29, 'recording_phase_would_reach_acquisition_cap')
        self.current.hold(seconds)

    def finish(self):
        if self.current is None:return
        current, self.current = self.current, None
        elapsed = self.clock() - self.started
        receipt = {'file': self.name, 'wall_seconds': elapsed, 'status': 'IN_PROGRESS'}
        self.receipts.append(receipt)
        try:
            receipt.update(current.finish())
            check(elapsed < 30 and 0 < receipt['seconds'] <= 30, 'recording_acquisition_cap_or_duration_failure')
            receipt['status'] = 'PASS_SCOPED_TECHNICAL'
        except Exception as error:
            receipt.update(status='FAIL', error_category=type(error).__name__)
            raise
        finally:self.save()


def runtime_identity(browser, root):
    pid = int(subprocess.check_output(['/usr/bin/systemctl', 'show', 'hermes-workspace-runtime.service',
                                     '-p', 'MainPID', '--value'], text=True, timeout=3))
    proc = Path('/proc') / str(pid)
    status = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
    argv = (proc / 'cmdline').read_bytes().split(b'\0')
    check(os.getuid() != 0 and status['Uid'].split() == [str(os.getuid())] * 4
          and status['CapEff'].strip() == '0000000000000000' and status['NoNewPrivs'].strip() == '1'
          and str(root / 'workspace/server.py').encode() in argv, 'actual_unprivileged_server_identity_required')
    expected = json.loads((root / 'workspace/ui/dist/identities.json').read_text())
    check(set(expected) == {'app.js', 'app.css'}, 'current_served_manifest_required')
    served = browser.evaluate("(async()=>{const out={};for(const name of ['app.js','app.css']){const r=await fetch('/assets/'+name,{cache:'no-store'});if(!r.ok)throw Error('served_asset_unavailable');const h=await crypto.subtle.digest('SHA-256',await r.arrayBuffer());out[name]=[...new Uint8Array(h)].map(n=>n.toString(16).padStart(2,'0')).join('')}return out})()")
    check(served == expected and all(hashlib.sha256((root / 'workspace/ui/dist' / name).read_bytes()).hexdigest() == value
                                     for name, value in expected.items()), 'actual_served_build_mismatch')
    return {'pid': pid, 'uid': os.getuid(), 'capabilities': status['CapEff'].strip(),
            'no_new_privileges': True, 'served_sha256': served,
            'start': (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=APP_ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-production-probe', action='store_true')
    parser.add_argument('--resume-after-permissions', type=Path, help='Continue an exact owned case whose permission checks already passed.')
    parser.add_argument('--resume-at', choices=('search','import','delete'), default='search')
    args = parser.parse_args()
    if not args.execute_production_probe:parser.error('review prepared source before explicitly executing the production probe')
    check(os.getuid() != 0, 'run_as_normal_operator_only')
    root = args.app_root.resolve(strict=True); sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import close_panels, prepare, native_pointer_check, enable_native_input
    from scripts.owned_action_review import OwnedActionReview, make_import_fixture
    from scripts.owned_native_picker import NativePickerDriver
    from workspace.capture import NativeWindowRecording
    from workspace.server import normal_profile_unchanged

    output = args.output
    check(not any(p.is_symlink() for p in (output, *output.parents)), 'review_output_symlink_refused')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    check(output.stat().st_uid == os.getuid() and not output.stat().st_mode & 0o077, 'private_review_output_required')
    target = output / 'run.json'; check(not target.exists(), 'preserve_existing_actions_attempt')
    navigation = json.loads((BASE / 'review/owned-navigation.json').read_text())
    report = {'status': 'IN_PROGRESS', 'scope': 'actual production pin18791; fresh owned operator cases, no model inference',
              'source_sha256_before': source_snapshot(root), 'recordings': [], 'native_pointer': [], 'cleanup': {},
              'production_execution': True, 'known_gaps': ['Human motion/listening approval remains unverified.',
                  'Separate native chooser pixels are not included in the Hermes-XID recordings.',
                  'This operator proposal sequence does not prove a model-proposed action or assistant inline citation.',
                  'Guest execution remains blocked; no host fallback is used.']}
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    save()
    b = review = clips = None; cursor = None; restored = False; phase = 'startup'
    def deadline(_signal, _frame):raise TimeoutError('owned_action_review_600_second_deadline')
    previous_alarm = signal.signal(signal.SIGALRM, deadline); signal.alarm(600)
    try:
        check(normal_profile_unchanged(), 'normal_profile_changed_before_review')
        b = ProductionPin(); b.reload_ready()
        report['runtime_before'] = runtime_identity(b, root); save()
        review = OwnedActionReview(b, rpc, output / 'owned', navigation)
        if args.resume_after_permissions:
            receipt = args.resume_after_permissions
            check(not receipt.is_symlink() and receipt.stat().st_size < 256 * 1024, 'bounded_regular_owned_receipt_required')
            prior = json.loads(receipt.read_text())
            required = ('default_execute_denied','legacy_write_denied','microphone_default_denied','explicit_deny_execute_denied','write_once_and_idempotent_replay','wrong_session_denied','custom_persists_across_models_reload','owned_only_workspace_files')
            check(all(prior['checks'].get(key) for key in required), 'prior_permission_sequence_not_complete')
            case = prior['case']
            check(case['nonce'].startswith(navigation['prefix'] + '-actions-') and 3 <= len(case['created_session_ids']) <= 5,
                  'exact_original_owned_case_required')
            review.case.update(case)
            review.report['checks'].update(prior['checks'])
            review.report['actions'].extend(prior['actions'])
            review.report['attachments_created'].extend(prior['attachments_created'])
            report['resumed_permissions_receipt'] = {'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'scope':'Previously measured permission sequence; not repeated or promoted to a new execution.'}
            review.save()
        else:review.create()
        review.select('permission_session'); review.assert_selected('permission_session')
        clips = RotatingRecordings(b, output, report['recordings'], save, NativeWindowRecording)
        def qualify(stage):
            nonlocal cursor
            native = getattr(b, '_native_input', None)
            if native:native.close(); b._native_input = None
            close_panels(b); prepare(b); proof = native_pointer_check(b)
            report['native_pointer'].append({'stage': stage, **proof}); save()
            check(proof['status'] == 'PASS', 'native_pointer_not_qualified')
            if cursor is None:cursor = b._native_initial_cursor
            enable_native_input(b)
        if not args.resume_after_permissions:
            phase = 'permissions'; qualify('permissions'); review.permissions()
        # Permissions reloads both model selections. Reinstall per-document
        # observers and requalify before recording rendered native motion.
        if args.resume_at == 'search':
            phase = 'Wikipedia'; qualify('Wikipedia'); clips.segment('wikipedia_request'); review.search_motion(clips); clips.finish()
        elif args.resume_after_permissions:
            check(review.report['checks'].get('real_Wikipedia_search',{}).get('state') == 'completed', 'actual_search_receipt_required_before_skip')
        else:raise RuntimeError('resume_stage_requires_prior_receipt')
        fixture_parent = BASE / 'review/owned-import-source' / output.name
        check(not any(p.is_symlink() for p in (fixture_parent, *fixture_parent.parents)), 'fixture_parent_symlink_refused')
        fixture_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fixture = make_import_fixture(fixture_parent, review.case['nonce'])
        report['fixture'] = {'relative_files_sha256': fixture['files'], 'nonce': fixture['nonce']}; save()
        identity = runtime_identity(b, root)
        driver = NativePickerDriver(identity['pid'], root / 'workspace/server.py')
        if args.resume_at != 'delete':
            phase = 'import'; review.import_motion(clips, fixture, driver, lambda:qualify('import_fresh_document')); clips.finish()
        else:check(bool(review.report['checks'].get('real_picker_preview_cancel_commit_copy_and_original_unchanged')), 'actual_import_receipt_required_before_skip')
        review.select('delete_session'); qualify('empty_delete')
        phase = 'empty_delete'; clips.segment('empty_delete_cancel_escape_commit'); review.delete_motion(clips); clips.finish()
        report['runtime_after'] = runtime_identity(b, root)
        check(report['runtime_after'] == report['runtime_before'], 'production_runtime_changed_during_review')
        check(all(value is not False for value in review.report['checks'].values()), 'owned_action_assertion_failed')
        report['sequence_completed'] = True
    except Exception as error:
        reason = str(error)
        report.update(status='FAIL', phase=phase, error_category=type(error).__name__, error_code=reason if reason.isidentifier() and len(reason) < 180 else type(error).__name__, error_detail=reason[:350])
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, previous_alarm)
        def restore():
            nonlocal restored
            review.restore(); restored = True
        def close_native():
            native = getattr(b, '_native_input', None)
            if native:native.close(); b._native_input = None
        def restore_cursor():
            if cursor:
                subprocess.run(['/usr/bin/hyprctl', 'dispatch', 'hl.dsp.cursor.move({x=' + str(round(cursor['x'])) +
                                ',y=' + str(round(cursor['y'])) + '})'], capture_output=True, check=True, timeout=4)
        def close_pin():
            if review is not None and not restored:b.detach_preserving_document()
            else:b.close()
        steps = []
        if clips:steps.append(('recording', clips.finish))
        if review:steps.append(('original_presentation', restore))
        if b:steps.extend([('native_input', close_native), ('cursor', restore_cursor), ('pin', close_pin)])
        steps.append(('normal_profile', lambda:check(normal_profile_unchanged(), 'normal_profile_changed_after_review')))
        report['cleanup'] = cleanup_steps(steps)
        try:
            report['source_sha256_after'] = source_snapshot(root)
            check(report['source_sha256_after'] == report['source_sha256_before'], 'source_changed_during_review')
            report['source_unchanged'] = True
        except Exception as error:
            report['source_unchanged'] = False
            report['source_verification_error_category'] = type(error).__name__
        if report.get('sequence_completed') and report['source_unchanged'] and all(item['status'] == 'ok' for item in report['cleanup'].values()):
            report['status'] = 'PASS_SCOPED_TECHNICAL'
        else:report['status'] = 'FAIL'
        if review:
            report['owned_case_report'] = 'owned/actions.json'
            report['remaining_scoped_gaps'] = review.report['gaps']
        save()
    print(json.dumps({'status': report['status'], 'report': str(target)}), flush=True)
    if report['status'] != 'PASS_SCOPED_TECHNICAL':raise SystemExit(2)


if __name__ == '__main__':main()
