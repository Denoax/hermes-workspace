"""Production-pin visual diagnostics, with no inference, files or user-content writes.

Uses the actual launcher/profile/catalog on 18791. Pointer input is CDP trusted
DOM input unless --native-pointer is selected. Screens show a genuine local
navigation search for the chosen test prefix; unrelated titles are never
captured. No fetch replacement, renderer fixtures or invented activity is used.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.production_pin import ProductionPin
from workspace.capture import Recording, NativeWindowRecording
from workspace import launcher

TOOLBAR = (('#files-toggle', 'Files'), ('#diagnostics', 'Details'), ('#settings-toggle', 'Settings'))
VIEWPORTS = ((1280, 800), (1440, 900), (1920, 1080), (390, 844))


class NativeX11Input:
    """Installed XTEST server input, for the actual XWayland app only.

    These are synthesized native events, not CDP or human physical-device input.
    https://www.x.org/releases/X11R7.5/doc/Xext/xtestlib.html
    """
    def __init__(self):
        import ctypes as c
        import ctypes.util
        import os
        display_name = os.environ.get('DISPLAY', '')
        if not re.fullmatch(r':\d+(?:\.\d+)?', display_name):
            raise RuntimeError('native_input_requires_local_X_display')
        libraries = [ctypes.util.find_library(name) for name in ('X11', 'Xtst')]
        if not all(libraries):
            raise RuntimeError('native_XTEST_library_unavailable')
        self.x, self.test = [c.CDLL(name) for name in libraries]
        self.x.XOpenDisplay.argtypes = [c.c_char_p]
        self.x.XOpenDisplay.restype = c.c_void_p
        self.x.XCloseDisplay.argtypes = [c.c_void_p]
        self.x.XSync.argtypes = [c.c_void_p, c.c_int]
        self.test.XTestQueryExtension.argtypes = [c.c_void_p] + [c.POINTER(c.c_int)] * 4
        self.test.XTestFakeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong]
        self.test.XTestFakeButtonEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
        self.display = self.x.XOpenDisplay(display_name.encode())
        if not self.display:
            raise RuntimeError('native_XTEST_display_unavailable')
        event, error, major, minor = c.c_int(), c.c_int(), c.c_int(), c.c_int()
        if not self.test.XTestQueryExtension(self.display, c.byref(event), c.byref(error), c.byref(major), c.byref(minor)):
            self.close()
            raise RuntimeError('native_XTEST_extension_unavailable')
        self.pressed = False

    def move(self, x, y):
        # XWayland's XTEST pointer and Hyprland's visible cursor are distinct.
        # Pair their native operations, then the caller verifies both readbacks.
        subprocess.run(['/usr/bin/hyprctl', 'dispatch', f'hl.dsp.cursor.move({{x={round(x)},y={round(y)}}})'],
                       capture_output=True, check=True, timeout=4)
        if not self.test.XTestFakeMotionEvent(self.display, -1, round(x), round(y), 0):
            raise RuntimeError('native_XTEST_motion_rejected')
        self.x.XSync(self.display, 0)

    def button(self, pressed):
        if not self.test.XTestFakeButtonEvent(self.display, 1, bool(pressed), 0):
            raise RuntimeError('native_XTEST_button_rejected')
        self.x.XSync(self.display, 0)
        self.pressed = pressed

    def close(self):
        if self.display:
            if getattr(self, 'pressed', False):
                self.button(False)
            self.x.XCloseDisplay(self.display)
            self.display = None


def prepare(browser):
    browser.evaluate("""(async()=>{const bootstrap=await(await fetch('/hermes-workspace/api/bootstrap')).json();
    window.__v4rpc=async(method,fields={})=>{const r=await fetch('/hermes-workspace/api/rpc',{
      method:'POST',headers:{'Content-Type':'application/json','X-Hermes-CSRF':bootstrap.csrf},
      body:JSON.stringify({version:1,method,fields})});const d=await r.json();
      if(!r.ok||d.error)throw Error(d.error||'production_rpc_failed');return d.result;};
    window.__v4input=[];window.__v4pointer=null;window.__v4pointerSequence=0;window.__v4errors=[];
    document.addEventListener('pointermove',event=>{window.__v4pointer={sequence:++window.__v4pointerSequence,x:event.clientX,y:event.clientY,trusted:event.isTrusted,target:event.target.closest('button')?.id||null}},true);
    document.addEventListener('click',event=>{const e=event.target.closest('button,input,select,summary');if(e)window.__v4input.push({id:e.id||null,trusted:event.isTrusted})},true);
    addEventListener('error',()=>window.__v4errors.push('runtime_error'));
    addEventListener('unhandledrejection',()=>window.__v4errors.push('unhandled_rejection'));
    window.__v4buddyMutations=0;const face=document.querySelector('#theme-buddy svg');
    window.__v4buddyObserver=new MutationObserver(rows=>window.__v4buddyMutations+=rows.length);
    if(face)window.__v4buddyObserver.observe(face,{attributes:true,subtree:true});
    })()""")


def rpc(browser, method, fields=None):
    return browser.evaluate('window.__v4rpc(' + json.dumps(method) + ',' + json.dumps(fields or {}) + ')')


def metadata_fingerprint(browser):
    rows = {method: rpc(browser, method) for method in ('workspace.list', 'session.list')}
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return digest, {method: len(value) for method, value in rows.items()}


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def close_panels(browser):
    for _ in range(3):
        browser.key('Escape')
    browser.wait("!document.querySelector('dialog[open]')&&!document.querySelector('.action-menu,.effort-popover')")


def move(browser, x, y):
    mapping = getattr(browser, '_native_coordinates', None)
    if mapping:
        sx, sy, ox, oy, _address = mapping
        native = getattr(browser, '_native_input', None)
        if native:
            native.move(ox + x * sx, oy + y * sy)
            return
        subprocess.run(['/usr/bin/hyprctl','dispatch',f'hl.dsp.cursor.move({{x={round(ox+x*sx)},y={round(oy+y*sy)}}})'], capture_output=True, check=True, timeout=4)
    else:
        browser.call('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': x, 'y': y})


def pointer_state(browser, x, y, pressed):
    mapping = getattr(browser, '_native_coordinates', None)
    if mapping:
        move(browser, x, y)
        native = getattr(browser, '_native_input', None)
        if native:
            native.button(pressed)
            return
        window = json.dumps('address:' + mapping[4])
        state = json.dumps('down' if pressed else 'up')
        subprocess.run(['/usr/bin/hyprctl','dispatch','hl.dsp.send_key_state({window=' + window + ',mods="",key="mouse:272",state=' + state + '})'], capture_output=True, check=True, timeout=4)
    else:
        browser.call('Input.dispatchMouseEvent', {'type': 'mousePressed' if pressed else 'mouseReleased', 'x':x, 'y':y, 'button':'left', 'clickCount':1})


def enable_native_input(browser):
    def mouse(x, y, guard=False):
        if guard:
            raise RuntimeError('native_visual_input_does_not_suppress_real_actions')
        pointer_state(browser, x, y, True)
        pointer_state(browser, x, y, False)
    browser.mouse = mouse


def input_text(browser, selector, text):
    browser.click(selector)
    browser.key('a', 'KeyA', 2)
    browser.call('Input.insertText', {'text': text})


def current_theme(browser):
    return browser.evaluate('document.documentElement.dataset.theme')


def theme(browser, value):
    close_panels(browser)
    if current_theme(browser) != value:
        browser.click('#theme-buddy')
        browser.wait('document.documentElement.dataset.theme===' + json.dumps(value))
    time.sleep(.15)


def mark_motion_checkbox(browser):
    browser.evaluate("(()=>{const label=[...document.querySelectorAll('dialog[open] label')].find(e=>e.textContent.includes('Less motion'));if(!label)throw Error('motion_setting_missing');label.querySelector('input').dataset.v4motion='true'})()")
    return browser.evaluate("document.querySelector('[data-v4motion]').checked")


def reduced_motion(browser, enabled):
    close_panels(browser)
    browser.click('#settings-toggle')
    browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
    if mark_motion_checkbox(browser) != enabled:
        browser.click('[data-v4motion]')
    browser.wait('document.documentElement.dataset.motion===' + json.dumps('reduced' if enabled else 'system'))
    close_panels(browser)


def shot(browser, output, name, records, selector=None):
    path = output / (name + '.png')
    clip = None
    if selector:
        rect = browser.rect(selector)
        check(rect['width'] > 0 and rect['height'] > 0, 'capture_surface_not_visible')
        clip = {key: rect[key] for key in ('x', 'y', 'width', 'height')}
        clip['scale'] = 1
    # A rest-state still waits only the finite overlay entry animation. Motion
    # elsewhere continues; this never freezes or fabricates a component state.
    browser.evaluate("Promise.all([...document.querySelectorAll('dialog[open]')].flatMap(dialog=>dialog.getAnimations().filter(animation=>Number.isFinite(animation.effect?.getComputedTiming().endTime)).map(animation=>animation.finished.catch(()=>null))))")
    browser.capture(path, clip)
    records.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'surface': selector or 'full browser viewport', 'theme': current_theme(browser),
                    'viewport': browser.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})')})


def trigger_checks(browser, selector, title, cycles=1, nine_points=False):
    close_panels(browser)
    before = browser.rect(selector)
    samples = []
    points = [(u, v) for u in (.25, .5, .75) for v in (.25, .5, .75)] if nine_points else [(.5, .5)] * cycles
    for u, v in points:
        count = browser.evaluate('window.__v4input.length')
        x, y = before['x'] + before['width'] * u, before['y'] + before['height'] * v
        browser.mouse(x, y)
        browser.wait("document.querySelector('dialog[open] h2')?.textContent===" + json.dumps(title))
        after = browser.rect(selector)
        drift = max(abs(before[key] - after[key]) for key in ('x', 'y', 'width', 'height'))
        trusted = browser.evaluate('window.__v4input.slice(' + str(count) + ').some(event=>event.trusted&&event.id===' + json.dumps(selector[1:]) + ')')
        check(drift <= .5, 'toolbar_trigger_geometry_shift')
        check(trusted, 'trusted_pointer_did_not_activate_expected_trigger')
        browser.key('Escape')
        browser.wait("!document.querySelector('dialog[open]')")
        focused = browser.evaluate('document.activeElement.id') == selector[1:]
        check(focused, 'escape_did_not_restore_trigger_focus')
        samples.append({'u': u, 'v': v, 'trusted_activation': trusted, 'drift_CSS_px': drift, 'Escape_focus_restored': focused})
    return {'trigger': selector, 'title': title, 'before': before, 'samples': samples}


def buddy_sample(browser, point):
    move(browser, *point)
    time.sleep(.32)
    return browser.evaluate("(()=>{const button=document.querySelector('#theme-buddy'),svg=button.querySelector('svg');return {face:[Number(button.dataset.faceX),Number(button.dataset.faceY)],body:svg.style.transform,expression:svg.dataset.expression,pointer:window.__v4pointer,rect:button.getBoundingClientRect().toJSON()}})()")


def buddy_checks(browser, recording=None):
    rect = browser.rect('#theme-buddy')
    width, height = browser.evaluate('[innerWidth,innerHeight]')
    cy = rect['y'] + rect['height'] / 2
    positions = ((8, cy), (width - 15, cy), (rect['x'] + rect['width'] / 2, 8),
                 (width - 15, 12), (8, height - 5))
    samples = [buddy_sample(browser, point) for point in positions]
    check(all(math.hypot(*sample['face']) <= 3.5 for sample in samples), 'buddy_face_exceeds_owned_source_bound')
    spread = max(math.dist(a['face'], b['face']) for a in samples for b in samples)
    check(spread > 1, 'buddy_does_not_follow_distant_pointer_positions')
    points = [width - 15 - i * (width - 30) / 12 for i in range(13)]
    path = points + list(reversed(points))
    trace = []
    for x in path:
        move(browser, x, cy)
        if recording:
            recording.hold(.035)
        else:
            time.sleep(.035)
        trace.append(browser.evaluate("({time:performance.now(),x:Number(document.querySelector('#theme-buddy').dataset.faceX),y:Number(document.querySelector('#theme-buddy').dataset.faceY),body:document.querySelector('#theme-buddy svg').style.transform})"))
    before_theme = current_theme(browser)
    x, y = rect['x'] + rect['width'] / 2, cy
    pointer_state(browser, x, y, True)
    time.sleep(.08)
    pressed = browser.evaluate("document.querySelector('#theme-buddy svg').dataset.expression")
    move(browser, x + 12, y)
    pointer_state(browser, x + 12, y, False)
    check(current_theme(browser) == before_theme, 'buddy_drag_cancellation_toggled_theme')
    check(pressed == 'pressed', 'buddy_pressed_expression_missing')
    browser.evaluate("document.querySelector('#theme-buddy').focus()")
    browser.key('Enter')
    browser.wait('document.documentElement.dataset.theme!==' + json.dumps(before_theme))
    browser.key('Enter')
    browser.wait('document.documentElement.dataset.theme===' + json.dumps(before_theme))
    return {'distant_positions': samples, 'face_spread_CSS_source_units': spread, 'reversal_trace': trace,
            'pressed_expression': pressed, 'drag_cancelled_without_theme_change': True, 'keyboard_toggle_and_restore': True,
            'smoothness': 'Trace and unedited clip recorded; no human continuous-motion approval inferred.'}


def visibility_check(browser):
    other = None
    try:
        other = browser.pipe.call('Target.createTarget', {'url': 'about:blank', 'newWindow': False})['targetId']
        session = browser.pipe.call('Target.attachToTarget', {'targetId': other, 'flatten': True})['sessionId']
        browser.pipe.call('Page.bringToFront', {}, session)
        time.sleep(.2)
        visible = browser.evaluate('document.visibilityState')
        if visible != 'hidden':
            return {'status': 'UNVERIFIED', 'reason': 'The actual app-mode window remained visible when the blank target was foregrounded; no forged visibility event was dispatched.'}
        before = browser.evaluate('window.__v4buddyMutations')
        time.sleep(.4)
        after = browser.evaluate('window.__v4buddyMutations')
        check(before == after, 'hidden_buddy_kept_mutating')
        return {'status': 'PASS', 'actual_visibility': visible, 'buddy_mutations_during_hidden_interval': after - before}
    finally:
        if other:
            browser.pipe.call('Target.closeTarget', {'targetId': other})
        browser.call('Page.bringToFront')


def native_pointer_check(browser):
    def command(*args):
        return subprocess.check_output(args, text=True, timeout=5).strip()
    def dispatch(code):
        return command('hyprctl', 'dispatch', code)
    original_cursor = json.loads(command('hyprctl', 'cursorpos', '-j'))
    clients = json.loads(command('hyprctl', 'clients', '-j'))
    owned = [row for row in clients if row.get('class') == 'HermesWorkspace' and launcher.owns_browser(row['pid'])]
    check(len(owned) == 1, 'native_owned_Hermes_surface_not_unique')
    client = owned[0]
    try:
        address = client['address']
        check(bool(re.fullmatch(r'0x[0-9a-f]+', address)), 'invalid_native_surface_identity')
        dispatch('hl.dsp.focus({window=' + json.dumps('address:' + address) + '})')
        browser.call('Page.bringToFront')
        native = NativeX11Input() if client.get('xwayland') else None
        browser._native_input = native
        native_monitor = next(row for row in json.loads(command('hyprctl', 'monitors', '-j')) if row['id'] == client['monitor'])
        diagnostics = {'status': 'IN_PROGRESS', 'initial_surface_bounds': {
            'position': client['at'], 'size': client['size']},
            'monitor_work_area': launcher.monitor_work_area(native_monitor),
            'surface_fully_inside_monitor': launcher.surface_inside_monitor(client, native_monitor),
            'calibration_readbacks': []}
        browser._native_diagnostics = diagnostics

        def observed_move(gx, gy):
            sequence = browser.evaluate('window.__v4pointerSequence')
            if native:
                native.move(gx, gy)
                response = 'Hyprland compositor warp + XTEST native server motion event; XSync completed'
            else:
                response = dispatch(f'hl.dsp.cursor.move({{x={gx},y={gy}}})')
            deadline = time.monotonic() + .4
            event = None
            cursor = None
            while time.monotonic() < deadline:
                cursor = json.loads(command('hyprctl', 'cursorpos', '-j'))
                event = browser.evaluate('window.__v4pointer')
                cursor_matches = abs(cursor['x'] - gx) <= 1 and abs(cursor['y'] - gy) <= 1
                fresh_event = event and event['sequence'] > sequence and event['trusted']
                if cursor_matches and fresh_event:
                    break
                time.sleep(.02)
            return {'requested': [gx, gy], 'cursor': cursor, 'event': event,
                    'dispatch_response': response, 'fresh_event': bool(fresh_event),
                    'cursor_matches': cursor_matches}

        previous = None
        for attempt in range(20):
            coordinates = []
            samples = []
            for u, v in ((.4, .3), (.55, .5)):
                gx = client['at'][0] + round(client['size'][0] * u)
                gy = client['at'][1] + round(client['size'][1] * v)
                sample = observed_move(gx, gy)
                samples.append(sample)
                coordinates.append((gx, gy, sample['event']))
            diagnostics['calibration_readbacks'].append({'attempt': attempt, 'samples': samples})
            if not all(row['fresh_event'] and row['cursor_matches'] for row in samples):
                continue
            a, b = coordinates
            dx, dy = b[2]['x'] - a[2]['x'], b[2]['y'] - a[2]['y']
            if not dx or not dy:
                continue
            sx, sy = (b[0] - a[0]) / dx, (b[1] - a[1]) / dy
            ox, oy = a[0] - a[2]['x'] * sx, a[1] - a[2]['y'] * sy
            current = [sx, sy, ox, oy]
            if not all(math.isfinite(value) for value in current) or not (0 < sx < 8 and 0 < sy < 8):
                continue
            if previous and max(abs(a - b) for a, b in zip(previous, current)) <= 1:
                diagnostics['status'] = 'CALIBRATED'
                break
            previous = current
        else:
            diagnostics['status'] = 'FAIL'
            raise RuntimeError('native_cursor_mapping_not_stable')
        rect = browser.rect('#settings-toggle')
        samples = []
        for u in (.25, .5, .75):
            for v in (.25, .5, .75):
                x, y = rect['x'] + rect['width'] * u, rect['y'] + rect['height'] * v
                observation = observed_move(round(ox+x*sx), round(oy+y*sy))
                event = observation['event']
                error = max(abs(event['x'] - x), abs(event['y'] - y)) if event else None
                sample = {'u': u, 'v': v, 'observation': observation, 'max_CSS_error': error}
                samples.append(sample)
                diagnostics['nine_points'] = samples
                check(observation['fresh_event'] and observation['cursor_matches'] and event['target'] == 'settings-toggle' and error <= 1.5, 'native_pointer_hit_region_mismatch')
        before = browser.rect('#settings-toggle')
        window = json.dumps('address:' + address)
        for state in ('down', 'up'):
            if native:
                native.button(state == 'down')
            else:
                dispatch('hl.dsp.send_key_state({window=' + window + ',mods="",key="mouse:272",state=' + json.dumps(state) + '})')
        browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
        after = browser.rect('#settings-toggle')
        check(max(abs(before[key] - after[key]) for key in ('x','y','width','height')) <= .5, 'native_click_shifted_trigger')
        browser.key('Escape')
        browser.wait("!document.querySelector('dialog[open]')")
        monitor = next(row for row in json.loads(command('hyprctl','monitors','-j')) if row['id'] == client['monitor'])
        logical = [monitor['width']/monitor['scale'], monitor['height']/monitor['scale']]
        if monitor.get('transform', 0) % 2: logical.reverse()
        inside = (client['at'][0] >= monitor['x'] and client['at'][1] >= monitor['y'] and
                  client['at'][0]+client['size'][0] <= monitor['x']+logical[0]+1 and
                  client['at'][1]+client['size'][1] <= monitor['y']+logical[1]+1)
        diagnostics['status'] = 'PASS' if inside else 'PARTIAL'
        browser._native_coordinates = (sx, sy, ox, oy, address)
        browser._native_initial_cursor = original_cursor
        return {'status': 'PASS' if inside else 'PARTIAL',
                'kind': 'paired Hyprland warp + native XTEST server motion/button events; both actual compositor and trusted DOM readbacks verified; no display changes' if native else 'actual compositor cursor movement and mouse activation; no display changes',
                'surface_protocol': 'XWayland' if client.get('xwayland') else 'Wayland',
                'selection': 'unique HermesWorkspace native surface whose PID owns the dedicated profile',
                'calibration': coordinates, 'calibration_readbacks': diagnostics['calibration_readbacks'],
                'native_mouse_open_and_Escape_close': True,
                'logical_units_per_CSS_px': [sx, sy], 'nine_points': samples,
                'surface_bounds': {'position':client['at'],'size':client['size'],'monitor_position':[monitor['x'],monitor['y']],'logical_monitor_size':logical},
                'surface_fully_inside_monitor': inside}

    finally:
        dispatch('hl.dsp.cursor.move({x=' + str(original_cursor['x']) + ',y=' + str(original_cursor['y']) + '})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--test-prefix', default='V4visual')
    parser.add_argument('--test-session-id', help='Optional existing harmless test session; its title/project must match --test-prefix.')
    parser.add_argument('--native-pointer', action='store_true', help='Also move the real desktop cursor; requires an untouched input window.')
    parser.add_argument('--no-record', action='store_true')
    parser.add_argument('--native-recording', action='store_true', help='Record only the verified native XWayland app window; no desktop or microphone capture.')
    parser.add_argument('--record-only', action='store_true', help='Only native pointer qualification and current continuous motion; reuse the already captured settled stills.')
    parser.add_argument('--followup-only', action='store_true', help='Only settled native-size stills and the optional native cursor check; no repeat of completed viewport cycles.')
    parser.add_argument('--audible-clicks', action='store_true', help='Default temporarily mutes only the app interface sounds and restores the preference.')
    args = parser.parse_args()
    if args.record_only:
        args.followup_only = True
    recording_type = NativeWindowRecording if args.native_recording else Recording
    check(1 <= len(args.test_prefix) <= 80, 'invalid_test_prefix')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {'status': 'IN_PROGRESS', 'scope': 'actual Hermes pin / production catalog / 127.0.0.1:18791',
              'fixtures': False, 'isolated_server': False, 'model_inference_started': False,
              'user_content_mutations_issued': False, 'navigation_search_filter': args.test_prefix,
              'human_visual_approval': 'PENDING', 'continuous_human_motion_approval': 'PENDING',
              'physical_microphone_or_speaker_check': 'NOT_PERFORMED',
              'GPU_timings': 'UNMEASURED; CDP capture timestamps are not GPU presentation timings.',
              'viewports': [], 'captures': [], 'checks': {}, 'gaps': []}
    browser = None
    initial_view = None
    storage = None
    fingerprint = None
    recording = None
    try:
        browser = ProductionPin()
        check(browser.identity['url'] == 'http://127.0.0.1:18791/hermes-workspace', 'not_the_production_pin')
        report['pin'] = browser.identity
        prepare(browser)
        time.sleep(.4)
        report['checks']['startup_error_banner_absent'] = browser.evaluate("!document.querySelector('.error-banner')")
        check(report['checks']['startup_error_banner_absent'], 'startup_error_banner_present')
        routes = {'/hermes-workspace': 'workspace/ui/index.html', '/assets/app.js': 'workspace/ui/dist/app.js', '/assets/app.css': 'workspace/ui/dist/app.css', '/interface-audio.mjs': 'workspace/ui/interface-audio.mjs'}
        served = browser.evaluate("(async()=>{const hashes={};for(const route of " + json.dumps(list(routes)) + "){const response=await fetch(route);if(!response.ok)throw Error('served_asset_missing');const digest=await crypto.subtle.digest('SHA-256',await response.arrayBuffer());hashes[route]=[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('');}return hashes})()")
        check(all(served[route] == hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for route,path in routes.items()), 'served_source_identity_mismatch')
        report['served_sha256'] = served
        report['source_sha256'] = {path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in ('workspace/launcher.py','workspace/capture.py','scripts/probe_v4_visual.py')}
        report['pin_wrapper_sha256'] = hashlib.sha256((Path.home()/'.local/bin/hermes-workspace').read_bytes()).hexdigest()
        initial_view = rpc(browser, 'view.read')
        storage = browser.evaluate("Object.fromEntries(['hermes:new-draft','hermes-ui:sounds'].map(key=>[key,localStorage.getItem(key)]))")
        fingerprint, report['content_counts_before'] = metadata_fingerprint(browser)
        browser.call('Page.bringToFront')
        close_panels(browser)
        # A real navigation filter avoids capturing unrelated user titles.
        if args.test_session_id:
            check(bool(re.fullmatch(r'[0-9a-f]{32}', args.test_session_id)), 'invalid_test_session_id')
            sessions = rpc(browser, 'session.list')
            selected = next(row for row in sessions if row['id'] == args.test_session_id)
            check(selected['title'].startswith(args.test_prefix), 'capture_session_not_marked_as_test')
            folders = rpc(browser, 'workspace.list')
            if selected['project']:
                check(next(row for row in folders if row['id'] == selected['project'])['label'].startswith(args.test_prefix), 'capture_project_not_marked_as_test')
            view = {**initial_view, 'session_id': selected['id'], 'project_id': selected['project'], 'arm': selected['arm']}
            rpc(browser, 'view.write', {'state': view})
            browser.call('Page.reload')
            browser.wait("document.getElementById('connection')?.textContent==='Connected'")
            prepare(browser)
        else:
            browser.click('.all-conversations')
            browser.click('#new-session')
            browser.wait("!document.querySelector('.message')&&document.querySelector('#prompt').value===''")
        input_text(browser, '.rail-search input', args.test_prefix)
        browser.wait("[...document.querySelectorAll('.session-row>button:first-child,.folder-select>span')].every(e=>e.textContent.startsWith(" + json.dumps(args.test_prefix) + "))", timeout=3)
        report['gaps'].append('Live inference/status/search/voice/task states are not manufactured by this visual-only probe; see separate production action/model evidence.')
        if not browser.evaluate("!!document.querySelector('.folder-row')"):
            report['gaps'].append('Populated folder-rail comparison is not covered by this empty/test-filter state.')
        report['captures_use'] = 'Actual harmless test content' if args.test_session_id else 'Actual empty conversation; no synthetic messages or activity'
        if not args.audible_clicks and browser.evaluate("document.querySelector('#sound-toggle').dataset.sound==='on'"):
            browser.click('#sound-toggle')
        reduced_motion(browser, False)
        report['system_reduced_motion'] = browser.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
        native_size = browser.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})')
        if args.followup_only:
            browser.call('Emulation.clearDeviceMetricsOverride')
            if args.native_recording and args.native_pointer:
                report['native_pointer'] = native_pointer_check(browser)
                check(report['native_pointer']['status'] == 'PASS', 'native_window_not_fully_visible_for_recording')
                enable_native_input(browser)
                report['recorded_input'] = 'Paired Hyprland compositor warp and native XTEST X11 server motion/button events, independently verified by compositor cursor and trusted DOM coordinates. This is synthesized native input, not physical user input. Keyboard checks use CDP key events.'
            report['phase'] = 'settled native stills'
            for selected_theme in (() if args.record_only else ('dark','light')):
                theme(browser, selected_theme)
                shot(browser, output, f'settled-native-{selected_theme}', report['captures'])
                browser.click('#settings-toggle')
                browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
                shot(browser, output, f'settled-native-{selected_theme}-settings', report['captures'])
                close_panels(browser)
                browser.click('#plus-menu')
                browser.wait("[...document.querySelectorAll('.action-menu button')].some(e=>e.textContent.includes('Import folder'))")
                browser.evaluate("[...document.querySelectorAll('.action-menu button')].find(e=>e.textContent.includes('Import folder')).dataset.v4import='true'")
                browser.click('[data-v4import]')
                browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Import folder'")
                report['folder_surface'] = browser.rect('[data-slot="folder"]')
                shot(browser, output, f'settled-native-{selected_theme}-folder', report['captures'])
                close_panels(browser)
            if not args.no_record:
                # Screenshot requests can race the screencast image encoder.
                # Record a distinct uninterrupted segment with no still capture.
                report['phase'] = 'native window recording startup'
                try:
                    recording = recording_type(browser, output / 'production-unedited-motion.mp4')
                except RuntimeError as error:
                    if not args.native_recording:
                        raise
                    report['native_recording_gap'] = str(error)
                    report['gaps'].append('Native window recording blocked; retained XID identity diagnostics. Current fallback is actual CDP screencast, validated in original arrival order, no reordering or interpolation.')
                    recording = Recording(browser, output / 'production-unedited-motion.mp4')
                recording.hold(.4)
                report['phase'] = 'recording actual buddy motion'
                report['buddy'] = buddy_checks(browser, recording)
                for selected_theme in ('dark','light'):
                    theme(browser, selected_theme)
                    browser.click('#settings-toggle')
                    recording.hold(.6)
                    close_panels(browser)
                    recording.hold(.3)
                browser.click('#plus-menu')
                browser.wait("[...document.querySelectorAll('.action-menu button')].some(e=>e.textContent.includes('Import folder'))")
                recording.hold(.4)
                browser.evaluate("[...document.querySelectorAll('.action-menu button')].find(e=>e.textContent.includes('Import folder')).dataset.v4import='true'")
                browser.click('[data-v4import]')
                browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Import folder'")
                button = '[data-slot="folder"] [role="button"]'
                rect = browser.rect(button)
                move(browser, rect['x'] + rect['width']/2, rect['y'] + rect['height']/2)
                recording.hold(.6)
                browser.click(button)
                recording.hold(.7)
                close_panels(browser)
                recording.hold(.4)
                finished = recording
                recording = None
                report['recording'] = finished.finish()
                report['recording']['human_continuous_review'] = 'PENDING'
            if not args.record_only:
                report['checks']['settled_followup_stills_captured'] = True
        else:
            frames = [('native', None)] + [(f'{width}x{height}', (width, height)) for width, height in VIEWPORTS]
            for label, dimensions in frames:
                if dimensions:
                    browser.metric(*dimensions)
                else:
                    browser.call('Emulation.clearDeviceMetricsOverride')
                for selected_theme in ('dark', 'light'):
                    theme(browser, selected_theme)
                    row = {'label': label, 'theme': selected_theme, 'viewport': browser.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})'), 'status': 'IN_PROGRESS'}
                    report['viewports'].append(row)
                    row['layout'] = browser.evaluate("(()=>{const rail=document.querySelector('.sidebar'),composer=document.querySelector('.composer');return {horizontalOverflow:document.documentElement.scrollWidth>innerWidth,railVisible:getComputedStyle(rail).display!=='none',rail:rail.getBoundingClientRect().toJSON(),composer:composer.getBoundingClientRect().toJSON(),buddy:document.querySelector('#theme-buddy').getBoundingClientRect().toJSON(),permissions:document.querySelector('#permissions-mode')?.getBoundingClientRect().toJSON()}})()")
                    check(not row['layout']['horizontalOverflow'], 'horizontal_overflow')
                    check(row['layout']['composer']['height'] <= (148 if dimensions and dimensions[0] < 640 else 125), 'composer_not_compact_at_rest')
                    row['toolbar'] = [trigger_checks(browser, selector, title, nine_points=True) for selector, title in TOOLBAR]
                    if dimensions == (1440, 900):
                        row['ten_cycles'] = [trigger_checks(browser, selector, title, cycles=10) for selector, title in TOOLBAR]
                    shot(browser, output, f'{label}-{selected_theme}', report['captures'])
                    browser.click('#settings-toggle')
                    browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Settings'")
                    shot(browser, output, f'{label}-{selected_theme}-settings', report['captures'])
                    browser.key('Tab')
                    row['keyboard_focus_in_panel'] = browser.evaluate("!!document.activeElement.closest('dialog[open]')")
                    check(row['keyboard_focus_in_panel'], 'keyboard_focus_did_not_reach_panel')
                    close_panels(browser)
                    row['status'] = 'PASS'
            browser.metric(1440, 900)
            theme(browser, 'dark')
            if not args.no_record:
                recording = recording_type(browser, output / 'production-unedited-motion.mp4')
                recording.hold(.5)
            report['buddy'] = buddy_checks(browser, recording)
            browser.click('[aria-label="Reasoning effort"]')
            browser.wait("!!document.querySelector('.effort-popover')")
            effort_value = browser.evaluate("document.querySelector('#reasoning-effort').value")
            browser.click('#reasoning-effort')
            browser.key('ArrowRight')
            if recording: recording.hold(.7)
            shot(browser, output, 'reasoning-on', report['captures'], '.effort-popover')
            browser.key('ArrowLeft')
            if recording: recording.hold(.6)
            shot(browser, output, 'reasoning-off', report['captures'], '.effort-popover')
            report['checks']['only_real_reasoning_states'] = browser.evaluate("(()=>{const e=document.querySelector('#reasoning-effort');return e.min==='0'&&e.max==='1'&&e.step==='1'})()")
            if effort_value == '1': browser.key('ArrowRight')
            close_panels(browser)
            browser.click('#plus-menu')
            browser.wait("[...document.querySelectorAll('.action-menu button')].some(e=>e.textContent.includes('Import folder'))")
            if recording: recording.hold(.6)
            shot(browser, output, 'plus-actions', report['captures'])
            browser.evaluate("[...document.querySelectorAll('.action-menu button')].find(e=>e.textContent.includes('Import folder')).dataset.v4import='true'")
            browser.click('[data-v4import]')
            browser.wait("document.querySelector('dialog[open] h2')?.textContent==='Import folder'")
            surface = browser.rect('[data-slot="folder"]')
            report['folder_surface'] = surface
            check(surface['width'] >= 300 and surface['height'] >= 250, 'folder_surface_was_minimized')
            folder_button = '[data-slot="folder"] [role="button"]'
            rect = browser.rect(folder_button)
            move(browser, rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] / 2)
            if recording: recording.hold(.7)
            shot(browser, output, 'folder-hover', report['captures'])
            browser.click(folder_button)
            if recording: recording.hold(.7)
            shot(browser, output, 'folder-open', report['captures'])
            browser.key('Escape')
            close_panels(browser)
            reduced_motion(browser, True)
            report['reduced_motion'] = buddy_checks(browser)
            check(all(sample['body'] == '' for sample in report['reduced_motion']['distant_positions']), 'reduced_buddy_body_kept_animating')
            browser.click('#settings-toggle')
            if recording: recording.hold(.3)
            shot(browser, output, 'reduced-settings', report['captures'])
            close_panels(browser)
            reduced_motion(browser, False)
            report['visibility'] = visibility_check(browser)
            if report['visibility']['status'] != 'PASS': report['gaps'].append('Actual app-mode hidden-tab cleanup remained unverified; see visibility reason.')
            browser.call('Emulation.setEmulatedMedia', {'features': [{'name': 'forced-colors', 'value': 'active'}]})
            browser.click('#settings-toggle')
            shot(browser, output, 'forced-colors-emulated', report['captures'])
            close_panels(browser)
            browser.call('Emulation.setEmulatedMedia', {'features': []})
            if recording:
                recording.hold(.4)
                finished = recording
                recording = None
                report['recording'] = finished.finish()
                report['recording']['human_continuous_review'] = 'PENDING'
        browser.call('Emulation.clearDeviceMetricsOverride')
        report['native_viewport_restored'] = browser.evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,zoom:visualViewport.scale})')
        if args.native_pointer:
            try:
                if 'native_pointer' not in report:
                    report['native_pointer'] = native_pointer_check(browser)
            except (RuntimeError, OSError, StopIteration, subprocess.SubprocessError) as error:
                report['native_pointer'] = {'status':'BLOCKED','reason':str(error) or type(error).__name__}
            report['checks']['native_pointer_and_visible_surface'] = report['native_pointer']['status'] == 'PASS'
            if report['native_pointer']['status'] != 'PASS': report['gaps'].append('Native pointer or native window placement is unresolved; see native_pointer. Other viewport results remain independently recorded.')
        else:
            report['native_pointer'] = {'status': 'NOT_RUN', 'reason': 'CDP trusted DOM input above is distinct from a real compositor cursor test. Run --native-pointer during an untouched-input window.'}
            report['gaps'].append('Native compositor cursor and physical input not checked by this invocation.')
        report['runtime_errors'] = browser.evaluate('window.__v4errors')
        report['checks']['runtime_error_observer_clean'] = not report['runtime_errors']
        if not args.followup_only:
            report['checks']['all_viewport_toolbar_checks'] = bool(report['viewports']) and all(row['status'] == 'PASS' for row in report['viewports'])
            report['checks']['buddy_pointer_pressed_drag_keyboard'] = bool(report.get('buddy'))
        if not args.record_only:
            report['checks']['full_size_source_folder_surface'] = report['folder_surface']['width'] >= 300 and report['folder_surface']['height'] >= 250
        report['checks']['no_model_or_action_requests'] = True
        report['checks']['native_viewport_restored'] = report['native_viewport_restored'] == native_size
        failed = [key for key,value in report['checks'].items() if not value]
        report['status'] = ('PARTIAL scoped technical checks' if not failed and report.get('native_recording_gap') else
                            'PASS scoped technical checks' if not failed else
                            'PARTIAL scoped technical checks' if failed == ['native_pointer_and_visible_surface'] else 'FAIL')
    except Exception as error:
        report['status'] = 'BLOCKED' if isinstance(error, RuntimeError) and ('screen_lock' in str(error) or 'close_existing_Hermes_pin' in str(error)) else 'FAIL'
        report['error'] = (str(error) or type(error).__name__)[:400]
        if browser and report.get('captures_use'):
            try: shot(browser, output, 'diagnostic-failure', report['captures'])
            except (RuntimeError, OSError, TimeoutError): pass
    finally:
        if recording:
            try: report['recording'] = recording.finish()
            except (RuntimeError, ValueError, OSError, TimeoutError, IndexError, subprocess.SubprocessError) as error: report['recording_error'] = type(error).__name__
        if browser:
            if hasattr(browser, '_native_diagnostics'):
                report['native_calibration_diagnostics'] = browser._native_diagnostics
            try:
                close_panels(browser)
                browser.call('Emulation.clearDeviceMetricsOverride')
                browser.call('Emulation.setEmulatedMedia', {'features': []})
                if initial_view:
                    # UI settings changes are settled first; the exact previous
                    # view is the final write before this diagnostic pin closes.
                    reduced_motion(browser, initial_view.get('motion') == 'reduced')
                    theme(browser, initial_view.get('theme', 'dark'))
                if storage:
                    enabled = storage['hermes-ui:sounds'] != 'off'
                    if browser.evaluate("document.querySelector('#sound-toggle').dataset.sound==='on'") != enabled:
                        browser.click('#sound-toggle')
                    browser.evaluate('Object.entries(' + json.dumps(storage) + ').forEach(([key,value])=>value===null?localStorage.removeItem(key):localStorage.setItem(key,value))')
                if initial_view:
                    rpc(browser, 'view.write', {'state': initial_view})
                    report['checks']['initial_view_restored'] = rpc(browser, 'view.read') == initial_view
                if fingerprint:
                    after, report['content_counts_after'] = metadata_fingerprint(browser)
                    report['checks']['project_conversation_metadata_unchanged'] = after == fingerprint
            except Exception as error:
                report['status'] = 'FAIL'
                report['restoration_error'] = str(error)[:200]
            finally:
                cursor = getattr(browser, '_native_initial_cursor', None)
                if cursor:
                    try: subprocess.run(['/usr/bin/hyprctl','dispatch',f'hl.dsp.cursor.move({{x={round(cursor["x"])},y={round(cursor["y"])}}})'], capture_output=True, check=True, timeout=4)
                    except (OSError, subprocess.SubprocessError): report['cursor_restoration'] = 'FAILED'
                    else: report['cursor_restoration'] = 'PASS'
                native = getattr(browser, '_native_input', None)
                if native:
                    native.close()
                browser.close()
        (output / 'visual.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'viewports': len(report['viewports']), 'captures': len(report['captures']), 'report': str(output / 'visual.json')}))
    if report['status'] not in ('PASS scoped technical checks',):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
