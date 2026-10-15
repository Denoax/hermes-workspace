"""Supplemental real-pin shell/reference checks; no new content records.

Reuses the full v4 visual helpers. This does not repeat their viewport/theme,
popover-reversal or buddy matrix. Browser200% zoom is a native accelerator with
readback;390px layout and CSS preference checks are explicitly emulated.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

APP_ROOT = Path(__file__).resolve().parents[1]
BASE = Path('/home/mani/mani-hermes-v5-6of3k6oz')


class Blocked(RuntimeError):
    """Unavailable prerequisite/input mechanism, distinct from product failure."""


def owned_case(value):
    if not isinstance(value,dict):
        raise ValueError('owned_navigation_object_required')
    if value.get('status') != 'PASS_SCOPED_TECHNICAL' or not re.fullmatch(r'V5review-[a-f0-9]{8}', value.get('prefix', '')):
        raise ValueError('positively_owned_navigation_case_required')
    projects, sessions = value.get('projects', []), value.get('sessions', [])
    if not isinstance(projects,list) or not isinstance(sessions,list) or not all(isinstance(row,dict) for row in [*projects,*sessions]):
        raise ValueError('owned_navigation_record_lists_required')
    marker = value['prefix']
    if any(not isinstance(row.get('label'),str) or marker not in row['label'] for row in projects) or any(not isinstance(row.get('title'),str) or marker not in row['title'] for row in sessions):
        raise ValueError('owned_navigation_labels_must_contain_nonce')
    ids = [row.get('id', '') for row in [*projects, *sessions]]
    if not ids or len(ids) != len(set(ids)) or not all(re.fullmatch(r'[a-f0-9]{32}', item) for item in ids):
        raise ValueError('unique_owned_record_IDs_required')
    selected = next((row for row in sessions if row['id']==value.get('selected_session_id')), None)
    project_ids = {row['id'] for row in projects}
    if not selected or selected.get('project') not in project_ids:
        raise ValueError('selected_session_must_belong_to_owned_project')
    return value['prefix'], selected


def retire_native_input(browser):
    """A failed or changed-scale calibration cannot leave usable old coordinates."""
    previous = getattr(browser, '_native_input', None)
    browser._native_input = None
    browser._native_coordinates = None
    if previous:
        previous.close()


def selected_rows(targeted):
    return ('R01_R02_native_motion', 'reduced_transparency_forced_colors_high_contrast') if targeted else None


def native_zoom_key(browser, launcher, symbol):
    """Fixed native XTEST browser accelerators; never device metric emulation."""
    if symbol not in ('0', 'equal', 'minus'):
        raise ValueError('fixed_browser_zoom_key_required')
    native = getattr(browser, '_native_input', None)
    if native is None:
        raise Blocked('native_XTEST_keyboard_unavailable')
    active = json.loads(subprocess.check_output(['/usr/bin/hyprctl','activewindow','-j'], text=True, timeout=4))
    if active.get('class') != 'HermesWorkspace' or not launcher.owns_browser(active.get('pid', 0)):
        raise Blocked('owned_pin_not_focused_for_native_accelerator')
    native.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
    native.x.XStringToKeysym.restype = ctypes.c_ulong
    native.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    native.x.XKeysymToKeycode.restype = ctypes.c_ubyte
    native.test.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    native.test.XTestFakeKeyEvent.restype = ctypes.c_int
    codes = [native.x.XKeysymToKeycode(native.display, native.x.XStringToKeysym(key.encode())) for key in ('Control_L', symbol)]
    if not all(codes):
        raise Blocked('native_zoom_keymap_unavailable')
    try:
        for code in codes:
            if not native.test.XTestFakeKeyEvent(native.display, code, 1, 0):
                raise Blocked('native_zoom_keypress_rejected')
        native.x.XSync(native.display, 0)
    finally:
        for code in reversed(codes):
            native.test.XTestFakeKeyEvent(native.display, code, 0, 0)
        native.x.XSync(native.display, 0)
    time.sleep(.18)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=APP_ROOT)
    parser.add_argument('--owned-case', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=BASE/'review/shell-supplemental')
    parser.add_argument('--execute-production-probe', action='store_true')
    parser.add_argument('--retry-failed-only', action='store_true', help='Repeat only R01/R02 native motion and CSS fallbacks; retain the full prior adverse receipt.')
    parser.add_argument('--fallback-only', action='store_true', help='Fresh-pin verification of only the CSS preference row after a zoom observer interruption.')
    parser.add_argument('--reference-theme', choices=('light','dark'), help='Capture only R01/R02 in the requested normal theme.')
    parser.add_argument('--layout-only', action='store_true', help='Final-build native and390px composer/navigation checks only.')
    parser.add_argument('--css-repair-only', action='store_true', help='Verify the observed footer/forced-color repairs without repeating model or reference-motion tests.')
    args = parser.parse_args()
    if not args.execute_production_probe:
        parser.error('private proposal: parent review and exclusive production pin window required')
    if os.geteuid() == 0:
        raise RuntimeError('normal_operator_required')
    if args.owned_case.is_symlink() or args.owned_case.stat().st_size>65536:
        raise ValueError('bounded_owned_navigation_receipt_required')
    prefix, selected = owned_case(json.loads(args.owned_case.read_text()))
    root = args.app_root.resolve(strict=True)
    sys.path.insert(0, str(root))
    from scripts.production_pin import ProductionPin
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import (
        close_panels, enable_native_input, input_text, move, native_pointer_check,
        pointer_state, prepare, reduced_motion, shot, theme, trigger_checks,
    )
    from workspace import launcher
    from workspace.capture import NativeWindowRecording

    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    if args.output.is_symlink() or output.stat().st_mode & 0o077:
        raise ValueError('owner_only_review_directory_required')
    target = output/'shell.json'
    if target.exists():
        history = output/'history'
        history.mkdir(mode=0o700, exist_ok=True)
        (history/('attempt-'+str(time.time_ns())+'.json')).write_bytes(target.read_bytes())
    sha = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'status':'IN_PROGRESS', 'scope':'actual18791 pin; supplemental checks only', 'rows':{},
              'owned_case_sha256':sha(args.owned_case), 'selected_session_id':selected['id'], 'prefix':prefix,
              'new_content_records_created':False, 'inference_started':False, 'captures':[], 'cleanup':{},
              'retry_failed_only':args.retry_failed_only, 'human_visual_approval':'PENDING', 'source_parity_1_to_1':'NOT_CLAIMED',
              'probe_sha256':sha(Path(__file__)),
              'source_sha256':{name:sha(root/name) for name in ('scripts/production_pin.py','scripts/probe_v4_visual.py','workspace/capture.py','workspace/frontend/src/main.tsx','workspace/frontend/src/controls.tsx','workspace/frontend/src/style.css','workspace/frontend/src/permissions.tsx')}}
    browser = recording = None
    initial_view = initial_draft = own_draft = policy_before = policy_changed = storage = initial_filter = None
    metadata_before = initial_geometry = native_base = None
    zoom_touched = leave_open = False
    initial_zoom_factor = 1
    phase = 'startup'

    def save():
        target.write_text(json.dumps(report, indent=2)+'\n')
        target.chmod(0o600)

    save()

    def evaluate(source):
        return browser.evaluate(source)

    def click(selector):
        nonlocal phase
        phase = 'click:' + selector
        evaluate('document.querySelector('+json.dumps(selector)+').scrollIntoView({block:"center",inline:"nearest"})')
        browser.click(selector)

    def geometry():
        return evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visual_scale:visualViewport.scale,css_zoom:getComputedStyle(document.documentElement).zoom})')

    def record(name, action):
        nonlocal recording
        try:
            report['rows'][name] = {'status':'PASS_SCOPED_TECHNICAL','result':action()}
        except Blocked as error:
            report['rows'][name] = {'status':'BLOCKED','reason':str(error)}
        except Exception as error:
            failure = {'status':'FAIL','error_type':type(error).__name__,
                       'code':str(error) if str(error).isidentifier() else 'supplemental_check_failed',
                       'phase':phase, 'error_message_sha256':hashlib.sha256(str(error).encode()).hexdigest()}
            # Geometry and DOM identities only: never include conversation text.
            try:
                failure['diagnostics'] = evaluate('(()=>{const e=document.querySelector("#settings-toggle"),r=e.getBoundingClientRect(),h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {width:innerWidth,height:innerHeight,dpr:devicePixelRatio,theme:document.documentElement.dataset.theme,motion:document.documentElement.dataset.motion,open_dialogs:[...document.querySelectorAll("dialog[open]")].map(e=>e.getAttribute("aria-label")),action_open:!!document.querySelector(".action-menu"),effort_open:!!document.querySelector(".effort-popover"),settings_rect:r.toJSON(),settings_hit:{tag:h?.tagName,id:h?.id},native_mapping_present:false}})()')
                failure['diagnostics']['native_mapping_present'] = bool(getattr(browser,'_native_coordinates',None))
                failure['native_calibration'] = getattr(browser,'_native_diagnostics',None)
            except Exception as diagnostic_error:
                failure['diagnostic_error_type'] = type(diagnostic_error).__name__
            report['rows'][name] = failure
        finally:
            if recording:
                partial,recording = recording,None
                try:
                    report['partial_recording'] = partial.finish()
                except Exception as error:
                    report['cleanup']['recording_error'] = type(error).__name__
        save()

    def filter_owned():
        input_text(browser, '.rail-search input', prefix)
        browser.wait('[...document.querySelectorAll(".session-row>button:first-child,.folder-select>span")].every(e=>e.textContent.includes('+json.dumps(prefix)+'))')

    def capture(name, selector=None):
        # Never click outside an open reference/control merely to reapply a
        # filter: that would close it and turn its screenshot into false proof.
        if evaluate('document.querySelector(".rail-search input").value')!=prefix:
            raise Blocked('capture_filter_not_in_owned_prefix')
        if rpc(browser,'view.read',{})['session_id']!=selected['id']:
            raise Blocked('capture_not_in_owned_session')
        shot(browser, output, name, report['captures'], selector)

    def fingerprint():
        rows = {name:rpc(browser,name,{}) for name in ('workspace.list','session.list')}
        return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()

    def composer(limit):
        if evaluate('document.querySelector("#prompt").value!==""||document.querySelectorAll("#composer .attachment").length>0'):
            raise Blocked('owned_composer_must_be_empty_for_height_measurement')
        metrics = evaluate('(()=>{const c=document.querySelector("#composer"),m=document.querySelector("#model-picker"),p=document.querySelector("#permissions-mode"),s=document.querySelector("#send");const v=e=>{const r=e.getBoundingClientRect(),a=getComputedStyle(e);return {x:r.x,y:r.y,width:r.width,height:r.height,visible:a.display!=="none"&&a.visibility!=="hidden"&&r.width>0&&r.height>0&&r.left>=-1&&r.right<=innerWidth+1&&r.top>=-1&&r.bottom<=innerHeight+1}};return {height:c.getBoundingClientRect().height,model:v(m),permissions:v(p),send:v(s),overflow:document.documentElement.scrollWidth>innerWidth+1}})()')
        if metrics['height'] > limit+1e-6 or metrics['overflow'] or not all(metrics[key]['visible'] for key in ('model','permissions','send')):
            raise RuntimeError('composer_height_or_essential_control_visibility_failed')
        return {'limit_css_px':limit, 'geometry':geometry(), **metrics}

    def narrow_composer():
        try:
            close_panels(browser)
            browser.metric(390,844,native_base['dpr'])
            if abs(geometry()['width']-390)>1:
                raise Blocked('390px_layout_override_not_verified')
            value = composer(112)
            capture('composer-390')
            click('.mobile-toggle')
            browser.wait('document.querySelector(".sidebar").classList.contains("mobile-open")')
            capture('navigation-390')
            browser.key('Escape')
            return {'scope':'responsive layout emulation only; not physical mobile', **value}
        finally:
            browser.call('Emulation.clearDeviceMetricsOverride')

    def settings_model():
        models = rpc(browser,'models.list',{})
        state = evaluate('(()=>{const e=document.querySelector("#model-picker"),r=e.getBoundingClientRect();return {value:e.value,title:e.title,label:e.selectedOptions[0]?.textContent,options:[...e.options].map(o=>o.value),visible:r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth}})()')
        expected = {m['id'] for m in models}
        if set(state['options']) != expected or not state['visible'] or state['value'] not in expected:
            raise RuntimeError('visible_model_inventory_not_exact_installed_set')
        current = next(m for m in models if m['id']==state['value'])
        if current['label'] not in state['title'] or current['label'] != state['label']:
            raise RuntimeError('installed_model_identity_title_missing')
        click('#settings-toggle')
        browser.wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]\')')
        value = evaluate('(()=>{const d=document.querySelector(\'dialog[open][aria-label="Settings"]\');return {interface:!!d.querySelector(\'[aria-label="Interface preferences"]\'),permissions:!!d.querySelector(".permission-settings"),groups:[...d.querySelectorAll(".settings-disclosure summary")].map(e=>e.textContent.trim()),credit:d.querySelector(".settings-credit")?.href}})()')
        if not value['interface'] or not value['permissions'] or not {'Local models','Capabilities'}.issubset(value['groups']) or value['credit'] != 'https://www.rareui.com/':
            raise RuntimeError('settings_groups_or_required_attribution_missing')
        capture('settings-groups', 'dialog[open][aria-label="Settings"]')
        close_panels(browser)
        return {'model':state,'settings':value,'inference':'none; inventory loads no weights'}

    def custom_policy():
        nonlocal policy_before, policy_changed
        policy_before = rpc(browser,'permissions.read',{'session_id':selected['id']})
        if not policy_before['available']['read']['available']:
            raise Blocked('owned_project_read_checkbox_unavailable')
        click('#settings-toggle')
        browser.wait('!!document.querySelector(\'dialog[open][aria-label="Settings"]\')')
        evaluate('(()=>{const e=[...document.querySelectorAll("label.permission-setting")].find(e=>e.querySelector("span")?.firstChild?.textContent.trim()==="Read project files and attached context")?.querySelector("input");if(!e)throw Error("read_checkbox_missing");e.dataset.v5Shell="read"})()')
        browser.wait('!document.querySelector(\'[data-v5-shell="read"]\').disabled')
        expected = {**policy_before['capabilities'],'read':not policy_before['capabilities']['read']}
        policy_changed = {'mode':'custom','capabilities':expected}
        click('[data-v5-shell="read"]')
        browser.wait('document.querySelector("#settings-permissions-mode").value==="custom"&&!document.querySelector(\'[data-v5-shell="read"]\').disabled')
        changed = rpc(browser,'permissions.read',{'session_id':selected['id']})
        if changed['mode']!='custom' or changed['capabilities']!=expected:
            raise RuntimeError('actual_UI_policy_change_not_server_held')
        close_panels(browser)
        other = 'abliterated' if evaluate('document.querySelector("#model-picker").value')=='normal' else 'normal'
        if other not in {m['id'] for m in rpc(browser,'models.list',{})}:
            raise Blocked('second_verified_installed_model_unavailable')
        evaluate('(()=>{const e=document.querySelector("#model-picker");e.value='+json.dumps(other)+';e.dispatchEvent(new Event("change",{bubbles:true}))})()')
        browser.wait('document.querySelector("#model-picker").value==='+json.dumps(other))
        browser.reload_ready()
        prepare(browser)
        filter_owned()
        after = rpc(browser,'permissions.read',{'session_id':selected['id']})
        if after['mode']!='custom' or after['capabilities']!=expected or evaluate('document.querySelector("#permissions-mode").value')!='custom':
            raise RuntimeError('custom_policy_lost_on_same_session_model_switch_reload')
        return {'session_id':selected['id'],'model_after':other,'mode':'custom','capabilities':expected,'version_before':policy_before['version'],'version_after':after['version'],'actions_dispatched':False}

    def zoom_to(factor):
        native_zoom_key(browser,launcher,'0')
        base = geometry()
        for _ in range(14):
            value = geometry()
            ratio = value['dpr']/base['dpr']
            if abs(ratio-factor) <= .025:
                return base, value
            native_zoom_key(browser,launcher,'equal' if ratio<factor else 'minus')
        raise Blocked('native_zoom_factor_not_reachable_or_readback_unavailable')

    def qualify_native():
        nonlocal phase
        phase = 'native:retire_stale_mapping_and_close_panels'
        retire_native_input(browser)
        close_panels(browser)
        # Escape removes modal interception before the nine-point real-pointer
        # check. Require the actual toolbar target and four stable rAF frames.
        phase = 'native:wait_for_unobscured_stable_settings_trigger'
        evaluate('(async()=>{const deadline=performance.now()+1500;let prior=null,stable=0;while(performance.now()<deadline){await new Promise(requestAnimationFrame);const e=document.querySelector("#settings-toggle"),r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);const now=[r.x,r.y,r.width,r.height];const same=prior&&now.every((v,i)=>Math.abs(v-prior[i])<=.25);stable=same&&hit?.closest("#settings-toggle")?stable+1:0;prior=now;if(stable>=4)return true}throw Error("native_settings_trigger_obscured_or_unstable")})()')
        phase = 'native:nine_point_calibration'
        try:
            value = native_pointer_check(browser)
        except RuntimeError as error:
            unavailable = {'native_input_requires_local_X_display','native_XTEST_library_unavailable',
                           'native_XTEST_display_unavailable','native_XTEST_extension_unavailable',
                           'native_cursor_mapping_not_stable','native_owned_Hermes_surface_not_unique'}
            if str(error) in unavailable:
                raise Blocked(str(error))
            retire_native_input(browser)
            raise
        if value['status']!='PASS':
            raise Blocked('native_surface_not_fully_qualified')
        enable_native_input(browser)
        phase = 'native:qualified'
        return value

    def actual_zoom():
        nonlocal zoom_touched, initial_zoom_factor
        browser.call('Emulation.clearDeviceMetricsOverride')
        qualify_native()
        before = geometry()
        native_zoom_key(browser,launcher,'0')
        baseline = geometry()
        initial_zoom_factor = before['dpr']/baseline['dpr']
        zoom_touched = True
        baseline, doubled = zoom_to(2)
        if abs(doubled['dpr']/baseline['dpr']-2)>.025 or abs(doubled['width']*2-baseline['width'])>4 or doubled['visual_scale']!=1 or doubled['css_zoom']!=baseline['css_zoom']:
            raise Blocked('real_browser_200percent_zoom_not_independently_verified')
        qualified = qualify_native()
        controls = [trigger_checks(browser,s,t) for s,t in (('#files-toggle','Files'),('#diagnostics','Details'),('#settings-toggle','Settings'))]
        value = composer(112 if doubled['width']<=500 else 96)
        footer = evaluate('(()=>{const rect=s=>document.querySelector(s).getBoundingClientRect().toJSON();return {button:rect("#theme-buddy"),body:rect("#theme-buddy .theme-buddy"),label:rect(".rail-footer>span"),sound:rect("#sound-toggle")}})()')
        if footer['label']['left'] < max(footer['button']['right'],footer['body']['right'])+2 or footer['label']['right'] > footer['sound']['left']:
            raise RuntimeError('enlarged_buddy_footer_text_overlap')
        capture('actual-browser-200-percent')
        return {'method':'native XTEST Ctrl+equal/Ctrl+0 browser accelerator; no device metric/page-scale/CSS-zoom substitution','initial':before,'100percent':baseline,'200percent':doubled,'native_pointer':qualified,'controls':controls,'composer':value,'footer_non_overlap':footer,'physical_human_keyboard':'not claimed'}

    def zoom_check():
        try:
            return actual_zoom()
        finally:
            if zoom_touched:
                zoom_to(initial_zoom_factor)

    def reference_motion():
        nonlocal recording, phase
        browser.call('Emulation.clearDeviceMetricsOverride')
        qualify_native()
        if evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'):
            raise Blocked('system_reduced_motion_enabled_reference_motion_unavailable')
        close_panels(browser)
        reduced_motion(browser,False)
        begun = time.monotonic()
        try:
            recording = NativeWindowRecording(browser,output/'R01-R02-native-unedited.mp4')
        except FileNotFoundError:
            raise Blocked('native_capture_tools_unavailable')
        except RuntimeError as error:
            if str(error).startswith(('native_recording_','native_window_recording_start_')):
                raise Blocked(str(error))
            raise
        click('[aria-label="Reasoning effort"]')
        phase = 'R01:wait_effort_panel'
        browser.wait('!!document.querySelector("#reasoning-effort")')
        slider = evaluate('(()=>{const e=document.querySelector("#reasoning-effort");return {min:e.min,max:e.max,step:e.step,disabled:e.disabled}})()')
        if slider['disabled']:
            raise Blocked('installed_backend_reasoning_not_supported')
        if (slider['min'],slider['max'],slider['step'])!=('0','1','1'):
            raise RuntimeError('reasoning_exposes_more_than_two_real_detents')
        click('#reasoning-effort')
        browser.key('ArrowLeft')
        browser.wait('document.querySelector("#reasoning-effort").value==="0"')
        recording.hold(.45)
        browser.key('ArrowRight')
        browser.key('ArrowRight')
        browser.wait('document.querySelector("#reasoning-effort").value==="1"')
        recording.hold(.5)
        on = evaluate('({lobes:getComputedStyle(document.querySelector(".effort-popover .brain-lobes")).opacity,brain:document.querySelector(".effort-popover .brain-thumb").getBoundingClientRect().toJSON(),track:document.querySelector(".effort-track").getBoundingClientRect().toJSON(),pixel_field:!!document.querySelector(".effort-field rect")})')
        if float(on['lobes'])<=0 or not on['pixel_field']:
            raise RuntimeError('R01_on_brain_silhouette_or_pixel_track_missing')
        capture('R01-on', '.effort-popover')
        rect = browser.rect('#reasoning-effort')
        x0,x1,y = rect['x']+rect['width']*.1,rect['x']+rect['width']*.9,rect['y']+rect['height']/2
        pointer_state(browser,x1,y,True)
        for index in range(5):
            move(browser,x1+(x0-x1)*index/4,y)
        pointer_state(browser,x0,y,False)
        browser.wait('document.querySelector("#reasoning-effort").value==="0"')
        recording.hold(.45)
        capture('R01-off', '.effort-popover')
        close_panels(browser)
        rect = browser.rect('#plus-menu')
        x,y = rect['x']+rect['width']/2,rect['y']+rect['height']/2
        move(browser,x,y)
        recording.hold(.55)
        def metal():
            return evaluate('({face:getComputedStyle(document.querySelector(".metal-face")).transform,rim:[...document.querySelectorAll(".metal-rim i")].map(e=>({transform:getComputedStyle(e).transform,animations:e.getAnimations().map(a=>({time:a.currentTime,state:a.playState}))})),button:document.querySelector("#plus-menu").getBoundingClientRect().toJSON()})')
        first = metal()
        recording.hold(.5)
        second = metal()
        if first['face']!='none' or second['face']!='none' or first['rim']==second['rim']:
            raise RuntimeError('R02_fixed_face_or_actual_reflection_motion_failed')
        pointer_state(browser,x,y,True)
        recording.hold(.16)
        pointer_state(browser,x,y,False)
        browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="true"')
        browser.key('Escape')
        click('#plus-menu')
        click('#plus-menu')
        browser.wait('document.querySelector("#plus-menu").getAttribute("aria-expanded")==="false"')
        recording.hold(.6)
        capture('R02-after-press-reverse', '#plus-menu')
        if time.monotonic()-begun>28:
            raise Blocked('native_motion_capture_budget_exhausted_before_full_sequence')
        completed,recording = recording,None
        return {'slider':slider,'R01_on':on,'R02_first':first,'R02_second':second,'recording':completed.finish(),'source_material_match':'human matched-scale comparison pending; authored CSS and motion measurements do not establish1:1parity'}

    def idle_sampler():
        sampler = root/'scripts/performance_sampler.js'
        if not sampler.is_file():
            raise Blocked('reviewed_shared_performance_sampler_not_applied')
        from scripts.performance_summary import summarize
        move(browser,geometry()['width']/2,100)
        time.sleep(.5)
        evaluate('('+sampler.read_text()+')({duration_ms:10000})')
        try:
            evaluate('globalThis.__hermesPerformanceProbe.mark({arm:"none",basis:"idle_observation",phase:"idle",run_id:null})')
            for _ in range(50):
                evaluate('document.visibilityState')
                time.sleep(.04)
        finally:
            raw = evaluate('globalThis.__hermesPerformanceProbe.stop("caller")')
        path = output/'R02-idle-raw.json'
        path.write_text(json.dumps(raw,indent=2)+'\n')
        path.chmod(0o600)
        return {'sampler_sha256':sha(sampler),'summary':summarize(raw),'scope':'actual whole-app idle CPU/browser callback work with R02 active; no isolated component/GPU/presentation cost or both-model performance claim'}

    def fallbacks():
        nonlocal phase
        browser.call('Emulation.clearDeviceMetricsOverride')
        qualify_native()
        rows = []
        for mode,feature,value in (('reduced-transparency','prefers-reduced-transparency','reduce'),('forced-colors','forced-colors','active'),('high-contrast-preference','prefers-contrast','more')):
            try:
                browser.call('Emulation.setEmulatedMedia',{'features':[{'name':feature,'value':value}]})
                if not evaluate('matchMedia('+json.dumps('('+feature+': '+value+')')+').matches'):
                    raise Blocked('browser_did_not_expose_'+feature)
                for color in ('light','dark'):
                    phase = 'fallback:' + mode + ':' + color + ':close_panels'
                    close_panels(browser)
                    theme(browser,color)
                    click('[aria-label="Reasoning effort"]')
                    phase = 'fallback:' + mode + ':' + color + ':wait_effort_panel'
                    browser.wait('!!document.querySelector("#reasoning-effort")')
                    state = evaluate('(()=>{const s=e=>{const c=getComputedStyle(document.querySelector(e));return {display:c.display,opacity:c.opacity,animation:c.animationName,backdrop:c.backdropFilter,color:c.color,background:c.backgroundColor}};return {panel:s(".effort-popover"),range:s("#reasoning-effort"),rim:s(".metal-rim i"),face:s(".metal-face"),forced_adjust:getComputedStyle(document.querySelector("#reasoning-effort")).forcedColorAdjust}})()')
                    if mode=='reduced-transparency' and (state['panel']['backdrop'] not in ('none','') or state['rim']['animation']!='none' or float(state['rim']['opacity'])!=0):
                        raise RuntimeError('reduced_transparency_did_not_remove_backdrop_and_reflection_work')
                    if mode=='forced-colors' and (float(state['range']['opacity'])<=0 or state['rim']['display']!='none' or state['forced_adjust']!='auto'):
                        raise RuntimeError('forced_color_native_control_or_material_fallback_failed')
                    browser.key('Escape')
                    data = composer(96)
                    selected_contrast = None
                    if mode=='forced-colors':
                        selected_contrast = evaluate(r'''(()=>{const linear=v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4};const rgb=s=>(s.match(/[\d.]+/g)||[]).slice(0,3).map(Number);const lum=s=>{const c=rgb(s).map(linear);return .2126*c[0]+.7152*c[1]+.0722*c[2]};return [...document.querySelectorAll('.folder-row.selected .folder-select>span,.folder-row.selected .folder-select>small,.session-row.selected>button:first-child')].map(e=>{const c=getComputedStyle(e);const a=lum(c.color),b=lum(c.backgroundColor);return {tag:e.tagName,color:c.color,background:c.backgroundColor,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),forced_adjust:c.forcedColorAdjust}})})()''')
                        if len(selected_contrast)<3 or any(row['contrast']<4.5 or row['forced_adjust']!='none' for row in selected_contrast):
                            raise RuntimeError('selected_forced_color_system_pair_or_opt_out_failed')
                    capture(mode+'-'+color)
                    rows.append({'mode':mode,'theme':color,'computed':state,'composer':data,'selected_text_contrast':selected_contrast})
            finally:
                browser.call('Emulation.setEmulatedMedia',{'features':[]})
        return {'scope':'browser-emulated CSS preferences only; no physical OS/AT/contrast-ratio certification',
                'selected_text_contrast_scope':'Computed system-pair check only; captured pixels must independently show readable selected names without text backplates.',
                'states':rows}

    try:
        try:
            browser = ProductionPin()
        except RuntimeError as error:
            if str(error) in {'production_pin_blocked_by_screen_lock','close_existing_Hermes_pin_before_fresh_launch'}:
                raise Blocked(str(error))
            raise
        report['pin'] = browser.identity
        routes = {'/assets/app.js':'workspace/ui/dist/app.js','/assets/app.css':'workspace/ui/dist/app.css'}
        served = evaluate('(async()=>{const result={};for(const route of '+json.dumps(list(routes))+'){const response=await fetch(route,{cache:"no-store"});if(!response.ok)throw Error("served_asset_missing");const h=await crypto.subtle.digest("SHA-256",await response.arrayBuffer());result[route]=[...new Uint8Array(h)].map(v=>v.toString(16).padStart(2,"0")).join("")}return result})()')
        if any(served[route]!=sha(root/path) for route,path in routes.items()):
            raise RuntimeError('served_assets_do_not_match_checkout_build')
        report['served_sha256'] = served
        initial_geometry = geometry()
        initial_view = rpc(browser,'view.read',{})
        initial_filter = evaluate('document.querySelector(".rail-search input").value')
        if evaluate('document.querySelectorAll("#composer .attachment").length'):
            leave_open = True
            raise Blocked('unowned_unsent_attachment_state_preserved')
        if initial_view.get('session_id'):
            initial_draft = rpc(browser,'draft.read',{'session_id':initial_view['session_id']})
        if evaluate('document.querySelector("#prompt").value') != (initial_draft['text'] if initial_draft else ''):
            leave_open = True
            raise Blocked('unowned_unsaved_draft_preserved')
        sessions = rpc(browser,'session.list',{})
        actual = next((s for s in sessions if s['id']==selected['id']),None)
        if not actual or actual['project']!=selected['project'] or prefix not in actual['title']:
            raise Blocked('actual_selected_record_not_proved_owned')
        project = next((row for row in rpc(browser,'workspace.list',{}) if row['id']==selected['project']),None)
        if not project or prefix not in project['label']:
            raise Blocked('actual_project_not_proved_owned')
        metadata_before = fingerprint()
        storage = evaluate('Object.fromEntries(["hermes-ui:sounds","hermes-ui:interface-volume"].map(k=>[k,localStorage.getItem(k)]))')
        rpc(browser,'view.write',{'state':{**initial_view,'session_id':selected['id'],'project_id':selected['project'],'arm':actual['arm']}})
        browser.reload_ready()
        prepare(browser)
        filter_owned()
        own_draft = rpc(browser,'draft.read',{'session_id':selected['id']})
        if evaluate('document.querySelector("#sound-toggle").dataset.sound==="on"'):
            click('#sound-toggle')
        native_base = geometry()
        requested_rows = selected_rows(args.retry_failed_only)
        if args.layout_only:
            requested_rows = ('composer_native','composer_390')
        elif args.reference_theme:
            theme(browser,args.reference_theme)
            requested_rows = ('R01_R02_native_motion',)
        elif args.fallback_only:
            requested_rows = ('reduced_transparency_forced_colors_high_contrast',)
        elif args.css_repair_only:
            requested_rows = ('composer_native','composer_390','actual_browser_200percent_zoom','reduced_transparency_forced_colors_high_contrast')
        for name,action in (
            ('composer_native',lambda:composer(96)),
            ('composer_390',narrow_composer),
            ('installed_model_and_settings_groups',settings_model),
            ('custom_policy_model_switch_reload',custom_policy),
            ('actual_browser_200percent_zoom',zoom_check),
            ('R01_R02_native_motion',reference_motion),
            ('R02_actual_idle_CPU_proxy',idle_sampler),
            ('reduced_transparency_forced_colors_high_contrast',fallbacks),
        ):
            if requested_rows is None or name in requested_rows:
                record(name,action)
    except Blocked as error:
        report.update(status='BLOCKED',reason=str(error))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,code=str(error) if str(error).isidentifier() else 'shell_probe_failed')
    finally:
        if recording:
            try:
                report['partial_recording'] = recording.finish()
            except Exception as error:
                report['cleanup']['recording_error'] = type(error).__name__
        if browser and not leave_open:
            def cleanup(name,action):
                try:
                    result = action()
                    report['cleanup'][name] = True if result is None else result
                except Exception as error:
                    report['cleanup'][name] = {'error_type':type(error).__name__}

            def restore_policy():
                if policy_before is None or policy_changed is None:
                    return True
                current = rpc(browser,'permissions.read',{'session_id':selected['id']})
                fields = {k:current[k] for k in ('mode','capabilities')}
                original = {k:policy_before[k] for k in ('mode','capabilities')}
                if fields==original:
                    return True
                if fields!=policy_changed:
                    raise Blocked('owned_policy_external_drift_preserved')
                rpc(browser,'permissions.update',{'session_id':selected['id'],'expected_version':current['version'],**original})
                restored = rpc(browser,'permissions.read',{'session_id':selected['id']})
                return all(restored[k]==policy_before[k] for k in original)

            cleanup('emulated_media_cleared',lambda:browser.call('Emulation.setEmulatedMedia',{'features':[]}))
            cleanup('device_metrics_cleared',lambda:browser.call('Emulation.clearDeviceMetricsOverride'))
            cleanup('owned_policy_mode_capabilities_restored_versions_advance',restore_policy)
            if zoom_touched:
                cleanup('original_browser_zoom_restored',lambda:zoom_to(initial_zoom_factor))

            def restore_view():
                if storage:
                    if evaluate('document.querySelector("#sound-toggle").dataset.sound==="on"') != (storage['hermes-ui:sounds']!='off'):
                        click('#sound-toggle')
                    evaluate('Object.entries('+json.dumps(storage)+').forEach(([k,v])=>v===null?localStorage.removeItem(k):localStorage.setItem(k,v))')
                if initial_view:
                    rpc(browser,'view.write',{'state':initial_view})
                    browser.reload_ready()
                    browser.wait('document.documentElement.dataset.theme==='+json.dumps(initial_view['theme'])+'&&document.documentElement.dataset.motion==='+json.dumps(initial_view['motion']))
                    input_text(browser,'.rail-search input',initial_filter or '')
                    if rpc(browser,'view.read',{})!=initial_view:
                        return False
                return (not initial_draft or rpc(browser,'draft.read',{'session_id':initial_view['session_id']})==initial_draft) and (not own_draft or rpc(browser,'draft.read',{'session_id':selected['id']})==own_draft)

            cleanup('exact_initial_view_theme_motion_sound_and_drafts_restored',restore_view)
            if metadata_before:
                cleanup('project_conversation_metadata_unchanged',lambda:fingerprint()==metadata_before)
        if browser:
            try:
                cursor = getattr(browser,'_native_initial_cursor',None)
                if cursor:
                    subprocess.run(['/usr/bin/hyprctl','dispatch',f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'],capture_output=True,timeout=4)
            except Exception as error:
                report['cleanup']['native_cursor_error'] = {'error_type':type(error).__name__}
            try:
                native = getattr(browser,'_native_input',None)
                if native:
                    native.close()
            except Exception as error:
                report['cleanup']['native_input_error'] = {'error_type':type(error).__name__}
            try:
                if leave_open:
                    browser.detach_preserving_document()
                    report['cleanup']['unowned_document_preserved_pin_open'] = True
                else:
                    browser.close()
                    report['cleanup']['production_browser_closed'] = True
            except Exception as error:
                report['cleanup']['browser_error'] = {'error_type':type(error).__name__}
        if report['status']=='IN_PROGRESS':
            states = [r['status'] for r in report['rows'].values()]
            report['status'] = 'FAIL' if 'FAIL' in states else ('PARTIAL' if 'BLOCKED' in states else 'PASS_SCOPED_TECHNICAL')
        if any(v is False or isinstance(v,dict) and 'error_type' in v for v in report['cleanup'].values()):
            report['status'] = 'FAIL'
        save()
    print(json.dumps({'status':report['status'],'report':str(target),'new_content_records':0,'model_inference':False}))
    if report['status']!='PASS_SCOPED_TECHNICAL':
        raise SystemExit(2)


if __name__=='__main__':
    main()
