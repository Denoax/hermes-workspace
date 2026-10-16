"""Explicitly gated import-only acceptance on the existing production Hermes pin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SOURCES = ('scripts/probe_v6_import.py','scripts/owned_v6_import.py','scripts/unassisted_native_picker.py',
           'scripts/owned_native_picker.py','scripts/owned_action_review.py','scripts/owned_v6_interactions.py',
           'scripts/production_pin.py','scripts/probe_v4_chat.py','scripts/probe_v4_visual.py',
           'scripts/probe_v5_owned_actions.py','scripts/settled_overlay.py',
           'scripts/v6_zoom_restore.py','scripts/v6_surface_review.py',
           'workspace/native_coordinates.py','workspace/capture.py','workspace/launcher.py','workspace/server.py','workspace/desktop.py',
           'workspace/native_picker.py','workspace/catalog.py','workspace/files.py',
           'workspace/frontend/src/main.tsx','workspace/frontend/src/controls.tsx',
           'workspace/frontend/src/AnchoredPopover.tsx','workspace/frontend/src/lib/composing-intent.ts',
           'workspace/frontend/src/lib/overlay-placement.ts','workspace/frontend/src/lib/reduced-motion.ts',
           'workspace/frontend/src/lib/workspace-surface.ts','workspace/frontend/src/lib/draft-selection.ts',
           'workspace/frontend/src/lib/use-draft-attachments.ts','workspace/frontend/src/style.css',
           'workspace/frontend/src/interaction-surfaces.css','workspace/frontend/src/components/folder-component.tsx',
           'workspace/ui/dist/identities.json','workspace/ui/dist/app.js','workspace/ui/dist/app.css')


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def source_snapshot(root):
    result = {}
    for name in SOURCES:
        path = root/name
        check(not any(p.is_symlink() for p in (path,*path.parents)), 'source_symlink_refused')
        info = path.stat()
        check(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1,
              'owned_regular_import_source_required')
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def bounded_json_file(path):
    check(not any(p.is_symlink() for p in (path,*path.parents)), 'input_symlink_refused')
    info = path.stat()
    check(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size <= 256*1024,
          'bounded_owned_regular_input_required')
    return json.loads(path.read_text())


def guard_source(root, plan):
    check(isinstance(plan,dict) and set(plan)=={'version','sources'} and plan['version']==1
          and isinstance(plan['sources'],dict) and set(plan['sources'])==set(SOURCES), 'exact_import_source_plan_required')
    check(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in plan['sources'].values()), 'source_sha256_required')
    actual = source_snapshot(root)
    check(actual == plan['sources'], 'import_source_changed_before_execution')
    return actual


def desktop_json(*arguments):
    return json.loads(subprocess.check_output(arguments, text=True, timeout=4))


def owned_base_window(launcher, *, expected=None, read_json=desktop_json):
    clients = read_json('/usr/bin/hyprctl', 'clients', '-j')
    check(isinstance(clients, list), 'base_window_clients_required')
    owned = [row for row in clients if isinstance(row, dict) and row.get('class') == 'HermesWorkspace'
             and launcher.owns_browser(row.get('pid', 0))]
    check(len(owned) == 1, 'unique_owned_base_window_required')
    client = owned[0]
    identity = {'address': client.get('address'), 'pid': client.get('pid')}
    check(isinstance(identity['address'], str) and re.fullmatch(r'0x[0-9a-f]+', identity['address'])
          and type(identity['pid']) is int and identity['pid'] > 1, 'exact_base_window_identity_required')
    check(expected is None or identity == expected, 'base_window_identity_changed')
    check(client.get('floating') is True and client.get('xwayland') is True
          and client.get('fullscreen', 0) == 0, 'normal_floating_base_window_required')
    monitors = read_json('/usr/bin/hyprctl', 'monitors', '-j')
    check(isinstance(monitors, list), 'base_window_monitors_required')
    matches = [row for row in monitors if isinstance(row, dict) and row.get('id') == client.get('monitor')]
    check(len(matches) == 1, 'current_base_window_monitor_required')
    monitor = matches[0]
    return client, {'identity': identity, 'position': client['at'], 'size': client['size'],
                    'monitor_id': monitor['id'], 'monitor_work_area': launcher.monitor_work_area(monitor),
                    'fully_inside_monitor': launcher.surface_inside_monitor(client, monitor)}


def setup_base_window(browser, launcher, record, *, read_json=desktop_json):
    client, before = owned_base_window(launcher, read_json=read_json)
    record.update(scope='owned_base_app_only_before_qualification_capture_or_chooser',
                  status='IN_PROGRESS', before=before, applied=False, chooser_focus_or_float_applied=False)
    if not before['fully_inside_monitor']:
        record['applied'] = True
        launcher.position_browser_window(browser.pipe, browser.target, client)
    _, after = owned_base_window(launcher, expected=before['identity'], read_json=read_json)
    record['after'] = after
    check(after['fully_inside_monitor'], 'base_window_still_outside_after_setup')
    record['status'] = 'PASS'
    return after['identity']


def qualify_native_pointer(browser, expected_identity):
    """One existing strict13-point pass, then actual Settings open/Escape.

    No per-point activation, refocusing, retries or relaxed error limits. The
    same qualifier already verifies current R01/R02 controls on this host.
    """
    from scripts.probe_v4_visual import NativeX11Input, enable_native_input
    from scripts.v6_zoom_restore import active_owned, qualify_points_once, command
    from scripts.v6_surface_review import require_owned_native_focus
    client = active_owned(browser)
    check({'address': client['address'], 'pid': client['pid']} == expected_identity,
          'same_setup_and_qualified_window_required')
    browser._native_initial_cursor = command('/usr/bin/hyprctl', 'cursorpos', '-j')
    browser._native_input = NativeX11Input()
    result = qualify_points_once(browser, browser._native_input, client)
    browser._native_diagnostics = {'status': 'IN_PROGRESS', 'point_observation': result}
    check(result['status'] == 'PASS_POINTS_ONLY', 'single_pass_native_points_not_qualified')
    browser._native_coordinates = (*result['mapping'], client['address'])
    enable_native_input(browser)
    before = browser.rect('#settings-toggle')
    require_owned_native_focus(browser)
    browser.click('#settings-toggle')
    browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
    after = browser.rect('#settings-toggle')
    check(max(abs(before[k] - after[k]) for k in ('x','y','width','height')) <= .5,
          'native_click_shifted_trigger')
    require_owned_native_focus(browser)
    browser.key('Escape')
    browser.wait("!document.querySelector('dialog[open]')")
    require_owned_native_focus(browser)
    browser._native_diagnostics['status'] = 'PASS'
    return {'status': 'PASS', 'surface_protocol': 'XWayland',
            'point_observation': result, 'native_mouse_open_and_Escape_close': True,
            'logical_units_per_CSS_px': result['mapping'][:2],
            'kind': 'Single strict13-point native XTEST/compositor/DOM pass and Settings activation; no refocus or physical-input claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--private-recovery',type=Path,required=True)
    parser.add_argument('--fixture-parent',type=Path,required=True)
    parser.add_argument('--navigation',type=Path,required=True)
    parser.add_argument('--navigation-sha256',required=True)
    parser.add_argument('--expected-source-map',type=Path,required=True)
    parser.add_argument('--resume-owned-import',type=Path)
    parser.add_argument('--resume-owned-import-sha256')
    parser.add_argument('--diagnose-picker-only',action='store_true')
    parser.add_argument('--execute-production-probe',action='store_true')
    args = parser.parse_args()
    if not args.execute_production_probe:
        parser.error('explicit actual-production execution flag required')
    if os.getuid()==0:
        parser.error('normal unprivileged operator required')
    if bool(args.resume_owned_import) != bool(args.resume_owned_import_sha256) or args.diagnose_picker_only and not args.resume_owned_import:
        parser.error('diagnostic resume requires an exact prior owned-case receipt and SHA')
    root = args.app_root.resolve(strict=True)
    source_before = guard_source(root,bounded_json_file(args.expected_source_map))
    navigation = bounded_json_file(args.navigation)
    check(re.fullmatch('[0-9a-f]{64}',args.navigation_sha256)
          and hashlib.sha256(args.navigation.read_bytes()).hexdigest()==args.navigation_sha256, 'verified_navigation_SHA_required')
    output, fixtures = args.output,args.fixture_parent
    check(not output.exists() or not any(output.iterdir()),'preserve_existing_import_output')
    for path in (output,fixtures):
        check(not any(p.is_symlink() for p in (path,*path.parents)), 'output_or_fixture_symlink_refused')
        path.mkdir(mode=0o700,parents=True,exist_ok=True)
        check(path.stat().st_uid==os.getuid() and not path.stat().st_mode&0o077, 'private_owned_output_or_fixture_required')
    check('private-state' not in fixtures.parts, 'fixture_must_not_use_sensitive_import_root')
    target = output/'run.json'
    check(not target.exists(),'preserve_previous_import_attempt')
    sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'scripts'))
    from scripts.owned_v6_import import OwnedImportReview, resumed_import_case, existing_import_fixture, picker_request_outcome
    from scripts.owned_action_review import make_import_fixture
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import prepare,enable_native_input,close_panels
    from scripts.probe_v5_owned_actions import RotatingRecordings,cleanup_steps,runtime_identity
    from scripts.unassisted_native_picker import NativePickerDriver
    from workspace.capture import NativeWindowRecording
    from workspace.server import normal_profile_unchanged
    from workspace import launcher
    report = {'status':'IN_PROGRESS','scope':'actual18791 existing pin; fresh import project/session only; no inference, model selection on user sessions, search or permission mutation',
              'source_sha256_before':source_before,'recordings':[],'native_pointer':[],'cleanup':{},
              'navigation_receipt_sha256':args.navigation_sha256,
              'remaining':['No chooser pixels/home filenames are recorded; clips acquire only the verified Hermes XID.',
                           'Native events are synthesized, not human physical input; visual/motion approval stays separate.',
                           'VM qualification, live microphone, reboot and all old ledger gaps are unaffected.']}
    def save():
        target.write_text(json.dumps(report,indent=2)+'\n');target.chmod(0o600)
    browser = review = clips = driver = None
    cursor = None; restored = False; phase = 'startup'
    def alarm(_signal,_frame):raise TimeoutError('import_acceptance_600_second_deadline')
    previous = signal.signal(signal.SIGALRM,alarm)
    previous_term = signal.signal(signal.SIGTERM,alarm)
    signal.alarm(600);save()
    try:
        check(normal_profile_unchanged(),'normal_profile_changed_before_import')
        browser = ProductionPin()
        browser.wait("!!document.querySelector('#prompt')&&!document.querySelector('#prompt').disabled")
        report['runtime_before'] = runtime_identity(browser,root);save()
        review = OwnedImportReview(browser,rpc,output/'owned',navigation,args.private_recovery)
        if args.resume_owned_import:
            prior=bounded_json_file(args.resume_owned_import)
            check(re.fullmatch('[0-9a-f]{64}',args.resume_owned_import_sha256) and hashlib.sha256(args.resume_owned_import.read_bytes()).hexdigest()==args.resume_owned_import_sha256, 'exact_resume_case_SHA_required')
            review.case.update(resumed_import_case(prior,review.prefix));review.save()
            report['resumed_owned_case_sha256']=args.resume_owned_import_sha256
        clips = RotatingRecordings(browser,output,report['recordings'],save,NativeWindowRecording)
        fixture = existing_import_fixture(fixtures,review.case['nonce']) if args.resume_owned_import else make_import_fixture(fixtures,review.case['nonce'])
        report['fixture_identity_scope']='Current exact owned fixture bytes verified; prior attempt did not retain a private inode receipt.' if args.resume_owned_import else 'Fresh exclusively created owned fixture.'
        report['fixture'] = {'nonce':fixture['nonce'],'relative_files_sha256':fixture['files']};save()
        def qualify():
            nonlocal cursor, driver
            native = getattr(browser,'_native_input',None)
            if native:native.close()
            browser._native_input = None
            close_panels(browser);prepare(browser)
            check(launcher.focus(), 'existing_pin_initial_activation_failed')
            check('base_window_setup' not in report, 'base_window_setup_must_be_once')
            report['base_window_setup'] = {}
            try:
                identity = setup_base_window(browser, launcher, report['base_window_setup'])
            finally:
                save()
            try:
                proof = qualify_native_pointer(browser, identity)
            except Exception:
                report['native_pointer_failure'] = getattr(browser, '_native_diagnostics', {})
                metadata = None
                report['native_pointer_failure']['document_state'] = browser.evaluate('({focused:document.hasFocus(),visibility:document.visibilityState,pointer_locked:!!document.pointerLockElement})')
                x11 = {}
                try:
                    from workspace.capture import owned_x11_window
                    owned_x11_window(x11)
                except RuntimeError as error:
                    code = str(error)
                    x11['error_code'] = code if re.fullmatch('[A-Za-z0-9_]{1,160}', code) else 'owned_X11_observation_failed'
                report['native_pointer_failure']['X11_bounds_observation'] = x11
                try:
                    from scripts.v6_zoom_restore import NativeMetadata
                    samples = report['native_pointer_failure'].get('point_observation', {}).get('body_samples', [])
                    if samples:
                        metadata = NativeMetadata()
                        report['native_pointer_failure']['owned_X11_metadata'] = metadata.snapshot(samples[-1]['requested_native'])
                    report['native_pointer_failure']['document_state'] = browser.evaluate('({focused:document.hasFocus(),visibility:document.visibilityState,pointer_locked:!!document.pointerLockElement})')
                except Exception as error:
                    report['native_pointer_failure']['metadata_error_category'] = type(error).__name__
                finally:
                    if metadata: metadata.close()
                save()
                raise
            report['native_pointer'].append(proof);save()
            _, after = owned_base_window(launcher, expected=identity)
            report['base_window_after_qualification'] = after;save()
            check(proof['status']=='PASS','native_pointer_not_qualified')
            check(after['fully_inside_monitor'], 'base_window_outside_after_qualification')
            if cursor is None:cursor = browser._native_initial_cursor
            enable_native_input(browser)
            # Parent-XID discovery needs the hydrated, qualified native surface.
            driver = NativePickerDriver(report['runtime_before']['pid'],root/'workspace/server.py',
                                        request_observer=lambda phase:picker_request_outcome(browser,args.private_recovery,phase))
        def use_picker(picker_phase, fixture_root):
            check(driver is not None, 'qualified_native_parent_required_before_picker')
            return driver(picker_phase, fixture_root)
        phase = 'unassisted_native_import'
        review.import_motion(clips,fixture,use_picker,qualify,stop_after_cancel=args.diagnose_picker_only);clips.finish()
        check(len(review.case['created_session_ids'])==1 and not review.case.get('project_id'), 'import_only_scope_expanded')
        check(len(review.report.get('native_picker',[]))==(1 if args.diagnose_picker_only else 3) and all(x.get('unassisted_parenting',{}).get('verified_transient_parent') is True
              and x['unassisted_parenting'].get('float_applied') is False and x['unassisted_parenting'].get('focus_applied') is False
              for x in review.report['native_picker']), 'all_three_unassisted_phases_required')
        report['runtime_after'] = runtime_identity(browser,root)
        check(report['runtime_after']==report['runtime_before'],'production_runtime_changed_during_import')
        report['sequence_completed'] = True
        report['scope_completed']='cancel_only_diagnostic_no_preview_or_copy' if args.diagnose_picker_only else 'full_three_phase_unassisted_import'
    except Exception as error:
        detail = str(error)
        report.update(phase=phase,error_category=type(error).__name__,error_code=detail if re.fullmatch('[a-zA-Z][a-zA-Z0-9_]{0,179}',detail) else 'observer_or_application_error')
        if driver is not None and getattr(driver,'last_failure',None):report['native_driver_failure'] = driver.last_failure
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous);signal.signal(signal.SIGTERM,previous_term)
        def restore():
            nonlocal restored
            review.restore();restored = True
        def close_native():
            native = getattr(browser,'_native_input',None)
            if native:native.close();browser._native_input = None
        def restore_cursor():
            if cursor:
                subprocess.run(['/usr/bin/hyprctl','dispatch','hl.dsp.cursor.move({x='+str(round(cursor['x']))+',y='+str(round(cursor['y']))+'})'],capture_output=True,check=True,timeout=4)
        def close_pin():
            if review is None or not restored:browser.detach_preserving_document()
            else:browser.close()
        steps = []
        if clips:steps.append(('recordings',clips.finish))
        if review:steps.append(('original_presentation',restore))
        if browser:steps.extend([('native_input',close_native),('cursor',restore_cursor),('pin',close_pin)])
        steps.append(('normal_profile',lambda:check(normal_profile_unchanged(),'normal_profile_changed_after_import')))
        report['cleanup'] = cleanup_steps(steps)
        try:
            report['source_sha256_after'] = source_snapshot(root)
            check(report['source_sha256_after']==source_before,'source_changed_during_import')
            report['source_unchanged'] = True
        except Exception as error:
            report['source_unchanged'] = False;report['source_verification_error_category'] = type(error).__name__
        if review:report['owned_case_report'] = 'owned/actions.json'
        report['status'] = ('PASS_SCOPED_DIAGNOSTIC_CANCEL_ONLY' if args.diagnose_picker_only else 'PASS_SCOPED_TECHNICAL') if report.get('sequence_completed') and report.get('source_unchanged') and all(x['status']=='ok' for x in report['cleanup'].values()) else 'FAIL'
        save()
    print(json.dumps({'status':report['status'],'report':str(target)}),flush=True)
    if report['status'] not in ('PASS_SCOPED_TECHNICAL','PASS_SCOPED_DIAGNOSTIC_CANCEL_ONLY'):raise SystemExit(2)


if __name__=='__main__':main()
