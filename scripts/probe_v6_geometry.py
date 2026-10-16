"""Bounded geometry/focus checks on existing positively owned interaction cases.

Read and apply $reference-led-design. Explicit opt-in; ONE ProductionPin only.
No case creation, submit, inference, deletion, native installation or display
configuration. All original presentation stays in separate private recovery.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time

ROOT = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1')
SIZES = ((1320, 900), (1280, 800), (1440, 900), (1920, 1080), (390, 844), (640, 420))
ID = re.compile(r'[a-f0-9]{32}')
NONCE = re.compile(r'V6interaction-[a-f0-9]{12}')
SHA256 = re.compile(r'[a-f0-9]{64}')
AGGREGATE = 'actual_interaction_subcheck_aggregate'
SUBCHECKS = ('empty_A_is_conversation', 'A_genuine_UTF8_draft_and_attachment',
             'new_conversation_visible_and_focused', 'composing_reload_and_breadcrumb_overview',
             'B_staged_rename_move_Cancel_preserves_A_and_B', 'explicit_B_Save_keeps_viewed_A_unchanged',
             'unselected_Q_Cancel_and_Save_preserve_A', 'D_actual_core_Cancel_Escape_and_confirm_only_known_empty',
             'stale_owned_E_error_never_adopts_A')
SOURCES = ('scripts/probe_v6_geometry.py', 'scripts/v6_surface_review.py', 'scripts/owned_v6_interactions.py',
           'scripts/v6_preferences_review.py', 'scripts/v6_motion_review.py',
           'scripts/production_pin.py', 'scripts/probe_v4_visual.py', 'scripts/probe_v5_shell.py',
           'scripts/probe_v5_owned_actions.py', 'scripts/settled_overlay.py', 'workspace/server.py',
           'workspace/desktop.py', 'workspace/native_picker.py', 'workspace/launcher.py',
           'workspace/frontend/src/main.tsx', 'workspace/frontend/src/controls.tsx',
           'workspace/frontend/src/AnchoredPopover.tsx', 'workspace/frontend/src/interaction-surfaces.css',
           'workspace/frontend/src/lib/workspace-surface.ts', 'workspace/frontend/src/style.css',
           'workspace/ui/dist/identities.json')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_artifact(value):
    require(isinstance(value, str) and 0 < len(value) <= 300 and '\\' not in value
            and all(ord(char) >= 32 for char in value), 'relative_receipt_artifact_required')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in value.split('/')),
            'relative_receipt_artifact_required')
    return path


def aggregate_identity(receipt):
    """Validate the explicit aggregate schema, without relabeling failed runs.

    The root's aggregator verifies the referenced bytes and stored values. This
    loader checks provenance structure; live record guards still run separately.
    """
    require(receipt.get('status') == 'PARTIAL' and receipt.get('interaction_subchecks_complete') is True,
            'complete_scoped_interaction_aggregate_required')
    require(isinstance(receipt.get('case'), dict) and isinstance(receipt['case'].get('records'), dict),
            'aggregate_original_case_required')
    subchecks, sources = receipt.get('subchecks'), receipt.get('receipts')
    require(isinstance(subchecks, dict) and set(subchecks) == set(SUBCHECKS)
            and isinstance(sources, list) and len(sources) == 2, 'all_nine_scoped_subchecks_and_two_receipts_required')
    identities = []
    for source in sources:
        require(isinstance(source, dict) and source.get('overall_status') in ('FAIL', 'PARTIAL', 'PASS_SCOPED_TECHNICAL'),
                'retained_original_run_status_required')
        artifact, run = relative_artifact(source.get('artifact')), relative_artifact(source.get('run_artifact'))
        require(artifact.parts[-2:] == ('owned', 'interactions.json') and run == artifact.parent.parent / 'run.json',
                'paired_original_receipt_artifacts_required')
        hashes = source.get('source_sha256')
        require(all(isinstance(source.get(key), str) and SHA256.fullmatch(source[key]) for key in ('sha256', 'run_sha256'))
                and isinstance(hashes, dict) and 0 < len(hashes) <= 256
                and all(isinstance(value, str) and SHA256.fullmatch(value) for value in hashes.values()),
                'retained_source_receipt_hashes_required')
        for path in hashes:
            relative_artifact(path)
        identities.append((str(artifact), source['sha256'], str(run), source['run_sha256']))
    require(len(set(identities)) == 2 and sources[0]['sha256'] != sources[1]['sha256']
            and sources[0]['run_sha256'] != sources[1]['run_sha256'], 'distinct_original_receipt_identities_required')
    referenced = set()
    for name in SUBCHECKS:
        row = subchecks[name]
        require(isinstance(row, dict) and row.get('outcome') == 'PASS'
                and type(row.get('source_receipt')) is int and 0 <= row['source_receipt'] < len(sources)
                and 'value' in row, 'scoped_subcheck_PASS_and_source_required')
        referenced.add(row['source_receipt'])
        value = row['value']
        if name == 'A_genuine_UTF8_draft_and_attachment':
            require(isinstance(value, dict) and isinstance(value.get('id'), str) and ID.fullmatch(value['id'])
                    and value.get('mime') == 'text/plain' and type(value.get('bytes')) is int and value['bytes'] > 0
                    and all(isinstance(value.get(key), str) and SHA256.fullmatch(value[key])
                            for key in ('sha256', 'draft_sha256')), 'real_A_attachment_subcheck_required')
        elif name == 'D_actual_core_Cancel_Escape_and_confirm_only_known_empty':
            target = receipt.get('case', {}).get('records', {}).get('D', {}).get('id')
            require(isinstance(value, dict) and isinstance(target, str) and ID.fullmatch(target)
                    and value.get('deleted_id') == target, 'exact_D_subcheck_target_required')
        elif name == 'stale_owned_E_error_never_adopts_A':
            target = receipt.get('case', {}).get('records', {}).get('E', {}).get('id')
            require(isinstance(value, dict) and isinstance(target, str) and ID.fullmatch(target)
                    and value.get('fault_deleted_id') == target and value.get('visible_alert') is True,
                    'exact_E_visible_error_subcheck_required')
        else:
            require(value is True, 'actual_true_subcheck_value_required')
    require(referenced == {0, 1}, 'both_original_receipts_must_supply_measured_subchecks')


def load_case(receipt):
    require(isinstance(receipt, dict), 'completed_actual_interaction_receipt_required')
    if receipt.get('kind') == AGGREGATE:
        aggregate_identity(receipt)
    else:
        require(receipt.get('status') == 'PASS_SCOPED_TECHNICAL', 'completed_actual_interaction_receipt_required')
    case = receipt.get('case')
    require(isinstance(case, dict) and isinstance(case.get('nonce'), str) and NONCE.fullmatch(case['nonce']), 'actual_interaction_nonce_required')
    created, before, records = case.get('created_ids'), case.get('before_session_ids'), case.get('records')
    require(isinstance(created, list) and isinstance(before, list) and isinstance(records, dict), 'creation_and_before_inventory_required')
    require(len(created) == len(set(created)) and all(isinstance(v, str) and ID.fullmatch(v) for v in created)
            and all(isinstance(v, str) and ID.fullmatch(v) for v in before), 'bounded_unique_creation_inventory_required')
    for role, kind, field in (('P', 'project', 'label'), ('Q', 'project', 'label'),
                              ('A', 'conversation', 'title'), ('B', 'conversation', 'title')):
        row = records.get(role)
        require(isinstance(row, dict) and row.get('kind') == kind and row.get('id') in created
                and isinstance(row.get(field), str) and row[field].startswith(case['nonce'] + ' · '), 'exact_owned_case_roles_required')
    require(records['A']['id'] != records['B']['id'] and not {records['A']['id'], records['B']['id']} & set(before), 'A_and_B_must_be_new_distinct_recorded_sessions')
    require(len({records[role]['id'] for role in ('P', 'Q', 'A', 'B')}) == 4, 'case_roles_must_have_distinct_IDs')
    if receipt.get('kind') == AGGREGATE:
        require(set(records) == {'P', 'Q', 'A', 'B', 'D', 'E'} and len(created) == 6
                and set(created) == {row.get('id') for row in records.values()}
                and not set(created) & set(before), 'exact_six_fresh_aggregate_records_required')
        for role in ('D', 'E'):
            row = records[role]
            require(row.get('kind') == 'conversation' and isinstance(row.get('title'), str)
                    and row['title'].startswith(case['nonce'] + ' · '), 'owned_D_and_E_aggregate_identity_required')
    return deepcopy(case)


def surface_case(case):
    return {'prefix': case['nonce'], 'before_session_ids': case['before_session_ids'],
            'created_session_ids': [row['id'] for row in case['records'].values() if row.get('kind') == 'conversation'],
            'viewed_session_id': case['records']['A']['id'], 'target_session_id': case['records']['B']['id']}


def native_size_plan(width, height, chrome, work_area, *, native_size):
    require((width, height) in SIZES, 'fixed_geometry_matrix_size_required')
    require(all(type(chrome.get(key)) in (int, float) and math.isfinite(chrome[key]) for key in ('outerWidth', 'outerHeight', 'innerWidth', 'innerHeight')), 'finite_browser_size_readback_required')
    require(len(native_size) == 2 and all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in native_size),
            'finite_native_surface_size_required')
    # Chromium's JS outerWidth includes decorations that are absent from both
    # this XWayland surface and Browser.setWindowBounds. Measure the actual
    # compositor-to-content difference rather than adding those decorations.
    target = [round(width + native_size[0] - chrome['innerWidth']),
              round(height + native_size[1] - chrome['innerHeight'])]
    require(all(value > 0 for value in target), 'positive_actual_outer_size_required')
    return {'status': 'READY' if target[0] <= work_area[2] and target[1] <= work_area[3] else 'BLOCKED',
            'requested_CSS': [width, height], 'requested_outer': target,
            'available_work_area': list(work_area), 'clamped': False}


def command(*args):
    return subprocess.check_output(args, text=True, timeout=4).strip()


def dispatch(code):
    subprocess.run(['/usr/bin/hyprctl', 'dispatch', code], check=True, capture_output=True, timeout=4)


def owned_client(launcher, address=None):
    rows = json.loads(command('/usr/bin/hyprctl', 'clients', '-j'))
    owned = [row for row in rows if row.get('class') == 'HermesWorkspace' and launcher.owns_browser(row.get('pid', 0))]
    require(len(owned) == 1 and (address is None or owned[0].get('address') == address), 'exact_single_owned_native_window_required')
    require(re.fullmatch(r'0x[a-f0-9]+', owned[0].get('address', '')), 'owned_native_address_required')
    return owned[0]


def configure_size(browser, launcher, width, height):
    """Address only the launcher's own floating window; never clamp a request."""
    client = owned_client(launcher)
    require(client.get('floating') and not client.get('fullscreen'), 'existing_floating_pin_required_no_global_rules')
    monitor = next(row for row in json.loads(command('/usr/bin/hyprctl', 'monitors', '-j')) if row['id'] == client['monitor'])
    chrome = browser.evaluate('({outerWidth,outerHeight,innerWidth,innerHeight})')
    plan = native_size_plan(width, height, chrome, launcher.monitor_work_area(monitor), native_size=client['size'])
    plan['initial_browser_geometry'] = chrome
    plan['initial_native_size'] = client['size']
    plan['monitor'] = {key: monitor.get(key) for key in ('id', 'name', 'width', 'height', 'scale', 'refreshRate', 'transform')}
    if plan['status'] == 'BLOCKED':
        plan['reason'] = 'Requested complete native surface exceeds actual monitor work area; no silent clamp or emulated native PASS.'
        return plan
    address = client['address']; window = json.dumps('address:' + address)
    outer_width, outer_height = plan['requested_outer']
    dispatch(f'hl.dsp.window.resize({{x={outer_width},y={outer_height},relative=false,window={window}}})')
    window_id = browser.pipe.call('Browser.getWindowForTarget', {'targetId': browser.target})['windowId']
    browser.pipe.call('Browser.setWindowBounds', {'windowId': window_id, 'bounds': {'width': outer_width, 'height': outer_height}})
    stable = 0
    for attempt in range(25):
        if attempt == 0 or not stable:
            dispatch('hl.dsp.window.center({window=' + window + '})')
        time.sleep(.06)
        actual = owned_client(launcher, address)
        value = browser.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})')
        inside = launcher.surface_inside_monitor(actual, monitor)
        exact = abs(value['width'] - width) <= 1 and abs(value['height'] - height) <= 1
        stable = stable + 1 if inside and exact else 0
        if stable >= 2:
            plan.update(status='PASS', actual=value, native_position=actual['at'], native_size=actual['size'], fully_inside_work_area=True)
            return plan
    plan.update(status='BLOCKED', reason='Actual compositor/browser configure did not satisfy requested dimensions and full visibility.', actual=value)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=ROOT)
    parser.add_argument('--owned-case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-recovery', type=Path, required=True)
    parser.add_argument('--execute-production-probe', action='store_true')
    parser.add_argument('--only', choices=('all', 'sheets', 'zoom', 'preferences'), default='all',
                        help='Narrow follow-up observations; each report states its scope and retains earlier attempts.')
    parser.add_argument('--variant', choices=tuple(f'{w}x{h}-{theme}' for w,h in SIZES for theme in ('dark','light')),
                        help='Check exactly one native size/theme without repeating the zoom observations.')
    parser.add_argument('--preference', action='append', choices=('reduced-motion','reduced-transparency','forced-colors','high-contrast'),
                        help='Limit preference-only follow-up to named features; prior results remain separate.')
    args = parser.parse_args()
    if not args.execute_production_probe or os.getuid() == 0:
        parser.error('explicit production probe flag and normal unprivileged operator required')
    if args.variant and args.only in ('zoom', 'preferences'):
        parser.error('--variant does not select a zoom or preference observation')
    if args.preference and args.only != 'preferences':
        parser.error('--preference requires --only preferences')
    require(not any(p.is_symlink() for p in (args.owned_case, *args.owned_case.parents))
            and args.owned_case.is_file() and args.owned_case.stat().st_size <= 1024 * 1024, 'bounded_regular_owned_receipt_required')
    receipt = json.loads(args.owned_case.read_text())
    case = load_case(receipt)
    root = args.app_root.resolve(strict=True); sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.owned_v6_interactions import OwnedInteractions, owned_row, selection_ids
    from scripts.v6_surface_review import SurfaceReview, browser_zoom_200, viewport
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import prepare, native_pointer_check, enable_native_input, close_panels, theme
    from scripts.probe_v5_shell import retire_native_input, native_zoom_key
    from scripts.probe_v5_owned_actions import cleanup_steps, runtime_identity
    from scripts.settled_overlay import settled_overlay
    from workspace import launcher
    from workspace.server import normal_profile_unchanged

    output = args.output
    require(not any(p.is_symlink() for p in (output, *output.parents)), 'output_symlink_refused')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    require(output.stat().st_uid == os.getuid() and not output.stat().st_mode & 0o077, 'owner_only_review_output_required')
    source_before = {name: digest(root / name) for name in SOURCES}
    report = {'status': 'IN_PROGRESS', 'scope': 'ONE actual existing production pin; existing owned review cases only; no inference, submit, deletion or case creation.',
              'owned_receipt_sha256': digest(args.owned_case), 'source_sha256_before': source_before,
              'observation_scope': args.only,
              'selected_native_variant': args.variant,
              'selected_preferences': args.preference,
              'variants': [], 'captures': [], 'native_qualification': [], 'cleanup': {},
              'unverified': ['Continuous motion/human approval, physical input/device/AT/listening, live model/guest tests and edges not actually reached remain separate.']}
    target = output / 'geometry.json'
    def save():
        target.write_text(json.dumps(report, indent=2) + '\n'); target.chmod(0o600)
    browser = owner = review = None
    original_client = cursor = original_zoom = original_100_dpr = None
    original_restored = False
    variant = None
    def deadline(_signal, _frame):
        raise TimeoutError('geometry_probe_900_second_deadline')
    old_alarm = signal.signal(signal.SIGALRM, deadline); old_term = signal.signal(signal.SIGTERM, deadline)
    signal.alarm(900); save()
    try:
        require(normal_profile_unchanged(), 'normal_configuration_changed_before_geometry')
        browser = ProductionPin()
        browser.wait("!!document.querySelector('#prompt')&&!document.querySelector('#prompt').disabled")
        report['runtime_before'] = runtime_identity(browser, root)
        original_client = owned_client(launcher)
        owner = OwnedInteractions(browser, rpc, output / 'preservation', args.private_recovery)
        # Constructor only snapshots presentation. No create()/prepare_a(), upload
        # or metadata mutation is called. Validate live identities BEFORE loading.
        for role in ('A', 'B', 'P', 'Q'):
            owned_row(case, role, rpc(browser, 'session.list' if role in ('A', 'B') else 'workspace.list', {}))
        owner.case = deepcopy(case); owner.report['case'] = owner.case; owner.report['scope'] = 'Existing positively owned case reused for geometry; no new records.'
        owner.save(); owner.select_a(); prepare(browser)
        def qualify():
            nonlocal cursor
            retire_native_input(browser)
            close_panels(browser)
            proof = native_pointer_check(browser)
            report['native_qualification'].append(proof); save()
            require(proof['status'] == 'PASS', 'native_pointer_not_fully_qualified')
            if cursor is None:
                cursor = browser._native_initial_cursor
            enable_native_input(browser)
            return proof
        def rpc_read(method, fields):
            require(method in ('view.read', 'draft.read', 'session.list'), 'read_only_surface_RPC_required')
            return rpc(browser, method, fields)
        def capture(name, _selector):
            require(variant is not None, 'capture_variant_required')
            privacy = None
            if args.only == 'preferences':
                from scripts.v6_motion_review import privacy_guard
                privacy = privacy_guard(owner, receipt)
            require(browser.evaluate("document.querySelector('.rail-search input').value===" + json.dumps(case['nonce']) + "&&[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')].every(e=>e.textContent.startsWith(" + json.dumps(case['nonce'] + ' · ') + '))'), 'nonce_filter_before_capture_required')
            settled = settled_overlay(browser)
            require(settled['status'] in ('settled', 'no_overlay'), 'capture_overlay_not_settled')
            directory = output / variant['name']; directory.mkdir(mode=0o700, exist_ok=True)
            short = re.sub('[^a-z0-9-]', '-', name.lower())[:60]
            path = directory / (str(len(report['captures']) + 1).zfill(3) + '-' + short + '.png')
            require(not path.exists(), 'capture_overwrite_refused')
            browser.capture(path)
            report['captures'].append({'file': str(path.relative_to(output)), 'sha256': digest(path), 'viewport': viewport(browser), 'overlay_guard': settled,
                                       'privacy_guard': privacy})
            save()
        review = SurfaceReview(browser, case=surface_case(case), rpc_read=rpc_read, requalify=qualify, capture=capture)
        review.fresh_native()
        initial_zoom = viewport(browser)
        native_zoom_key(browser, launcher, '0')
        baseline_zoom = viewport(browser)
        original_100_dpr = baseline_zoom['dpr']
        original_zoom = initial_zoom['dpr'] / baseline_zoom['dpr']
        review.fresh_native()
        def hydrated_a():
            value = owner.a_state()
            return value['ui']['text'] == value['draft']['text'] and value['ui']['count'] == len(selection_ids(value['selection']))
        owner.poll(hydrated_a, 'owned_A_draft_and_attachment_metadata_not_hydrated')
        owner.a_baseline = owner.a_state()
        def reflow_baseline(stage):
            value, baseline = owner.a_state(), owner.a_baseline
            require(all(value[key] == baseline[key] for key in ('session', 'project', 'arm', 'draft', 'selection'))
                    and all(value['ui'][key] == baseline['ui'][key] for key in ('text', 'model', 'count')),
                    'A_data_changed_during_native_layout_reflow')
            report.setdefault('layout_reading_samples', []).append({'stage': stage,
                'before_CSS_px': baseline['ui']['scroll'], 'after_CSS_px': value['ui']['scroll'],
                'scope': 'Empty owned conversation reflows during an actual size/zoom change; each subsequent surface must preserve its own measured position.'})
            baseline['ui']['scroll'] = value['ui']['scroll']
        def drawer(opened):
            actual = browser.evaluate("document.querySelector('.sidebar')?.classList.contains('mobile-open')??false")
            if actual != opened:
                selector = '[aria-label="Open navigation"]' if opened else '[aria-label="Close navigation"]'
                review.click(selector)
                browser.wait("!!document.querySelector('.sidebar.mobile-open')===" + json.dumps(opened))
        def inspect_variant():
            if args.only == 'sheets':
                review.sheets()
                owner.assert_a()
                return
            narrow = browser.evaluate("(()=>{const e=document.querySelector('[aria-label=\"Open navigation\"]');return !!e&&e.getClientRects().length>0})()")
            review.popover('#plus-menu', '#composer-actions')
            review.popover('#effort-toggle', '#effort-options', menu=False)
            if narrow:
                drawer(True)
            try:
                trigger = '#conversation-options-' + case['records']['B']['id']
                browser.evaluate('document.querySelector(' + json.dumps(trigger) + ').scrollIntoView({block:"nearest"})')
                review.popover(trigger, '#row-actions', outside='.rail-search input')
                review.owned_management_modal()
                review.owned_management_modal(deletion_review=True)
            finally:
                close_panels(browser)
                if narrow:
                    drawer(False)
            review.click('#settings-toggle')
            review.modal_opened('Settings', return_selector='#settings-toggle')
            review.sheets()
            owner.assert_a()
        for width, height in (() if args.only in ('zoom', 'preferences') else SIZES):
            for appearance in ('dark', 'light'):
                if args.variant and args.variant != f'{width}x{height}-{appearance}':
                    continue
                variant = {'name': f'native-{width}x{height}-{appearance}', 'status': 'IN_PROGRESS', 'requested': [width, height]}
                report['variants'].append(variant); save()
                try:
                    close_panels(browser); retire_native_input(browser)
                    variant['native_size'] = configure_size(browser, launcher, width, height)
                    if variant['native_size']['status'] != 'PASS':
                        variant['status'] = 'BLOCKED'; continue
                    review.fresh_native()
                    theme(browser, appearance)
                    owner.poll(lambda: rpc(browser, 'view.read', {}).get('theme') == appearance,
                               'theme_not_persisted_before_geometry')
                    reflow_baseline(variant['name'])
                    owner.assert_a()
                    start = len(review.rows)
                    variant['checks'] = []
                    try:
                        inspect_variant()
                    finally:
                        variant['checks'] = review.rows[start:]
                    variant['status'] = 'PASS_SCOPED_TECHNICAL'
                except Exception as error:
                    code = str(error)
                    variant.update(status='FAIL', error_category=type(error).__name__, error_code=code if re.fullmatch('[A-Za-z0-9_:;.-]{1,256}', code) else 'observer_or_application_error')
                    if any(word in code for word in ('focus_drift', 'cursor_mapping', 'pointer_hit_region')):
                        raise
                finally:
                    save()
        if args.only == 'preferences':
            from scripts.v6_preferences_review import review_preferences
            from scripts.v6_motion_review import privacy_guard
            variant = {'name': 'native-emulated-preferences', 'status': 'IN_PROGRESS', 'checks': []}
            report['variants'].append(variant); save()
            start = len(review.rows)
            try:
                privacy_guard(owner, receipt)
                def set_theme(color):
                    review.close(); theme(browser, color)
                    owner.poll(lambda: rpc(browser, 'view.read', {}).get('theme') == color,
                               'theme_not_persisted_before_preference_review')
                result = review_preferences(review, assert_owned_a=owner.assert_a, set_theme=set_theme, names=args.preference)
                variant['status'] = 'BLOCKED' if result['status'] == 'PARTIAL_EMULATED' else 'PASS_SCOPED_TECHNICAL'
                privacy_guard(owner, receipt)
            except Exception:
                variant['status'] = 'FAIL'
                raise
            finally:
                variant['checks'] = review.rows[start:]; save()
        if args.only not in ('sheets', 'preferences') and not args.variant:
            close_panels(browser); retire_native_input(browser)
            report['pre_zoom_native_size'] = configure_size(browser, launcher, 1320, 900)
            require(report['pre_zoom_native_size']['status'] == 'PASS', 'native_baseline_unavailable_for_true_zoom')
            review.fresh_native()
            variant = {'name': 'native-browser-200-percent', 'status': 'IN_PROGRESS', 'checks': []}
            report['variants'].append(variant); save()
            start = len(review.rows)
            try:
                with browser_zoom_200(review) as proof:
                    variant['zoom'] = proof
                    for appearance in ('dark', 'light'):
                        theme(browser, appearance)
                        owner.poll(lambda: rpc(browser, 'view.read', {}).get('theme') == appearance,
                                   'theme_not_persisted_before_geometry')
                        reflow_baseline('native-browser-200-percent-' + appearance)
                        owner.assert_a(); inspect_variant()
                variant['status'] = 'PASS_SCOPED_TECHNICAL'
            except Exception:
                variant['status'] = 'FAIL'
                raise
            finally:
                variant['checks'] = review.rows[start:]; save()
        report['runtime_after'] = runtime_identity(browser, root)
        require(report['runtime_after'] == report['runtime_before'], 'production_runtime_changed_during_geometry')
        report['sequence_completed'] = True
    except Exception as error:
        code = str(error)
        report.update(error_category=type(error).__name__, error_code=code if re.fullmatch('[A-Za-z0-9_:;.-]{1,256}', code) else 'observer_or_application_error')
        if browser:
            report['last_native_diagnostics'] = getattr(browser, '_native_diagnostics', {})
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old_alarm); signal.signal(signal.SIGTERM, old_term)
        def restore_window():
            if original_client:
                client = owned_client(launcher, original_client['address']); window = json.dumps('address:' + client['address'])
                width, height = original_client['size']; x, y = original_client['at']
                window_id = browser.pipe.call('Browser.getWindowForTarget', {'targetId': browser.target})['windowId']
                dispatch(f'hl.dsp.window.resize({{x={width},y={height},relative=false,window={window}}})')
                browser.pipe.call('Browser.setWindowBounds', {'windowId': window_id, 'bounds': {'left': x, 'top': y, 'width': width, 'height': height}})
                for _ in range(20):
                    current = owned_client(launcher, original_client['address'])
                    if all(abs(a - b) <= 1 for a, b in zip(current['size'] + current['at'], [width, height, x, y])):
                        return
                    time.sleep(.06)
                raise RuntimeError('original_owned_window_bounds_not_restored')
        def restore_zoom():
            if original_zoom is None:
                return
            if abs(viewport(browser)['dpr'] / original_100_dpr - original_zoom) <= .025:
                return
            close_panels(browser)
            native_zoom_key(browser, launcher, '0'); base = viewport(browser)
            for _ in range(14):
                value = viewport(browser); ratio = value['dpr'] / base['dpr']
                if abs(ratio - original_zoom) <= .025:
                    return
                native_zoom_key(browser, launcher, 'equal' if ratio < original_zoom else 'minus')
            raise RuntimeError('original_browser_zoom_not_restored')
        def restore_presentation():
            nonlocal original_restored
            # Viewport changes may legitimately clamp owned empty A's reading
            # position. Its final draft/selection must still equal the last
            # observed baseline; original user presentation is separately CAS held.
            if owner.a_baseline is not None and rpc(browser, 'view.read', {}).get('session_id') == owner.case['records']['A']['id']:
                reflow_baseline('restore-original-native-size')
            owner.restore(); original_restored = True
        def release_native():
            retire_native_input(browser)
        def restore_cursor():
            if cursor:
                dispatch(f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})')
        def close_owned_pin():
            if original_restored:
                browser.close()
            else:
                browser.detach_preserving_document()
        steps = []
        if browser:
            steps += [('browser_zoom', restore_zoom), ('native_window', restore_window)]
        if owner:
            steps += [('original_presentation', restore_presentation)]
        if browser:
            steps += [('native_input', release_native), ('cursor', restore_cursor), ('owned_pin', close_owned_pin)]
        steps += [('normal_configuration', lambda: require(normal_profile_unchanged(), 'normal_configuration_changed_after_geometry'))]
        report['cleanup'] = cleanup_steps(steps)
        report['source_sha256_after'] = {name: digest(root / name) for name in SOURCES}
        report['source_unchanged'] = report['source_sha256_after'] == source_before
        counts = {status: sum(row['status'] == status for row in report['variants']) for status in ('PASS_SCOPED_TECHNICAL', 'BLOCKED', 'FAIL', 'IN_PROGRESS')}
        report['counts'] = counts
        complete = report.get('sequence_completed') and report['source_unchanged'] and all(row['status'] == 'ok' for row in report['cleanup'].values())
        report['status'] = ('PARTIAL' if counts['BLOCKED'] else 'PASS_SCOPED_TECHNICAL') if complete and not counts['FAIL'] and not counts['IN_PROGRESS'] else 'FAIL'
        save()
    print(json.dumps({'status': report['status'], 'report': str(target)}), flush=True)
    if report['status'] == 'FAIL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
