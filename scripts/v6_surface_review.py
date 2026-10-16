"""Focused checks inside an already exclusively owned actual Hermes pin.

Read and apply $reference-led-design. This module creates no browser, server,
catalog record, RPC mutation, media, model request or approval. Root supplies the
existing ProductionPin, a positively owned case, read-only RPC callback, and a
fresh native pointer qualification after each actual window/zoom change.
"""
from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
import ctypes
import hashlib
import json
import math
import re
import subprocess

ORIGIN = 'http://127.0.0.1:18791/hermes-workspace'
VIEWPORTS = ((1320, 900), (1280, 800), (1440, 900), (1920, 1080), (390, 844), (640, 420))
ID = re.compile(r'[a-f0-9]{32}')
COMPOSING_INTENT = 'hermes-ui:composing-intent:v1'
STORAGE_KEYS = ('hermes-ui:sounds', 'hermes-ui:interface-volume', 'hermes:new-draft',
                'hermes:draft-attachments:v1:new', COMPOSING_INTENT)


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def recorded(method):
    """Retain a failed check's partial measurements before propagating failure."""
    @wraps(method)
    def run(self, *args, **kwargs):
        row = {'kind': method.__name__, 'status': 'IN_PROGRESS'}
        self.rows.append(row)
        try:
            result = method(self, *args, **kwargs)
        except BaseException as error:
            code = str(error)
            row.update(status='FAIL', error_category=type(error).__name__,
                       error_code=code if re.fullmatch(r'[A-Za-z0-9_:;.-]{1,256}', code) else 'see_private_outer_error')
            raise
        row.update(result, status='PASS')
        return row
    return run


def rect_edges(rect):
    result = {key: rect[key] for key in ('x', 'y', 'width', 'height')}
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in result.values()):
        raise ValueError('finite_rect_required')
    if result['width'] <= 0 or result['height'] <= 0:
        raise ValueError('visible_nonempty_rect_required')
    return {**result, 'left': result['x'], 'top': result['y'],
            'right': result['x'] + result['width'], 'bottom': result['y'] + result['height']}


def assess_popover(before, after, surface, viewport, inset=8, drift_limit=1):
    """Independent measured invariants, not a second placement implementation."""
    first, anchor, panel = map(rect_edges, (before, after, surface))
    drift = max(abs(first[key] - anchor[key]) for key in ('x', 'y', 'width', 'height'))
    left, top = viewport['left'], viewport['top']
    width, height = viewport['width'], viewport['height']
    margins = {'left': panel['left'] - left, 'top': panel['top'] - top,
               'right': left + width - panel['right'], 'bottom': top + height - panel['bottom']}
    distance = max(max(anchor['left'] - panel['right'], panel['left'] - anchor['right'], 0),
                   max(anchor['top'] - panel['bottom'], panel['top'] - anchor['bottom'], 0))
    failures = []
    if drift > drift_limit:
        failures.append('trigger_drift_over_1_CSS_px')
    if min(margins.values()) < inset - .5:
        failures.append('surface_outside_8_CSS_px_visual_viewport_inset')
    if distance > 8.5:
        failures.append('surface_detached_from_visible_trigger')
    return {'status': 'PASS' if not failures else 'FAIL', 'failures': failures,
            'trigger_drift_CSS_px': drift, 'margins_CSS_px': margins,
            'anchor_surface_separation_CSS_px': distance}


def owns_case(case, sessions):
    if not isinstance(case, dict) or not re.fullmatch(r'(?:V6review-[a-f0-9]{8}(?:-[a-z0-9-]+)?|V6interaction-[a-f0-9]{12})', case.get('prefix', '')):
        raise ValueError('positively_owned_v6_nonce_required')
    created = case.get('created_session_ids', [])
    before = case.get('before_session_ids')
    viewed, target = case.get('viewed_session_id'), case.get('target_session_id')
    if (not isinstance(created, list) or not isinstance(before, list) or not created
            or len(created) != len(set(created)) or not all(isinstance(value, str) and ID.fullmatch(value) for value in created)
            or set(created) & set(before) or viewed == target or viewed not in created or target not in created):
        raise ValueError('new_distinct_owned_view_and_management_targets_required')
    by_id = {row['id']: row for row in sessions}
    for sid in (viewed, target):
        row = by_id.get(sid)
        if not row or case['prefix'] not in row.get('title', ''):
            raise ValueError('live_owned_session_identity_not_confirmed')
    return viewed, target


def require_owned_native_focus(browser):
    native = getattr(browser, '_native_input', None)
    mapping = getattr(browser, '_native_coordinates', None)
    require(native is not None and mapping is not None, 'fresh_native_XTEST_qualification_required')
    from workspace import launcher
    active = json.loads(subprocess.check_output(['/usr/bin/hyprctl', 'activewindow', '-j'], text=True, timeout=4))
    require(active.get('class') == 'HermesWorkspace' and active.get('address') == mapping[4]
            and launcher.owns_browser(active.get('pid', 0)), 'native_keyboard_or_pointer_focus_drift_abort')
    return native


def native_key(browser, key, *, shift=False, wait_for_dom=True):
    """Fixed XTEST navigation keys; owner/focus checked before every operation.

    These are native synthesized events, never physical-device/human evidence.
    The existing native pointer helper owns and releases the X connection.
    """
    allowed = {'Tab', 'Escape', 'Return', 'space', 'Up', 'Down', 'Left', 'Right', 'Home', 'End'}
    if key not in allowed and not re.fullmatch(r'[a-z]', key):
        raise ValueError('fixed_navigation_or_typeahead_key_required')
    native = require_owned_native_focus(browser)
    expected = {'Return': 'Enter', 'space': ' ', 'Up': 'ArrowUp', 'Down': 'ArrowDown',
                'Left': 'ArrowLeft', 'Right': 'ArrowRight'}.get(key, key)
    sequence = browser.evaluate('(()=>{const s=window.__v6SurfaceKeyReview;s.expected=' + json.dumps(expected if wait_for_dom else None) + ';return s.sequence})()')
    native.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
    native.x.XStringToKeysym.restype = ctypes.c_ulong
    native.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    native.x.XKeysymToKeycode.restype = ctypes.c_ubyte
    native.test.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    native.test.XTestFakeKeyEvent.restype = ctypes.c_int
    symbols = (['Shift_L'] if shift else []) + [key]
    codes = [native.x.XKeysymToKeycode(native.display, native.x.XStringToKeysym(value.encode())) for value in symbols]
    require(all(codes), 'native_navigation_keymap_unavailable')
    try:
        for code in codes:
            require(native.test.XTestFakeKeyEvent(native.display, code, 1, 0), 'native_navigation_keypress_rejected')
        native.x.XSync(native.display, 0)
    finally:
        for code in reversed(codes):
            native.test.XTestFakeKeyEvent(native.display, code, 0, 0)
        native.x.XSync(native.display, 0)
    if wait_for_dom:
        browser.wait('window.__v6SurfaceKeyReview.sequence>' + str(sequence))
    browser.evaluate('(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);return true})()')


def viewport(browser):
    return browser.evaluate('''(()=>{const v=visualViewport;return {
      left:v?.offsetLeft??0,top:v?.offsetTop??0,width:v?.width??innerWidth,height:v?.height??innerHeight,
      innerWidth,innerHeight,dpr:devicePixelRatio,visual_scale:v?.scale??1,css_zoom:getComputedStyle(document.documentElement).zoom,
      screen:[screen.width,screen.height],theme:document.documentElement.dataset.theme}})()''')


def capture_context(browser, rpc_read):
    """Private in-memory values only. Public reports get booleans/hashes."""
    view = rpc_read('view.read', {})
    sid = view.get('session_id')
    keys = list(STORAGE_KEYS)
    if sid:
        require(isinstance(sid, str) and ID.fullmatch(sid), 'current_session_ID_invalid')
        keys.append('hermes:draft-attachments:v1:' + sid)
    return {'view': deepcopy(view), 'draft': rpc_read('draft.read', {'session_id': sid}) if sid else None,
            'storage': browser.evaluate('Object.fromEntries(' + json.dumps(keys) + '.map(k=>[k,localStorage.getItem(k)]))'),
            'prompt': browser.evaluate('document.querySelector("#prompt")?.value??null'),
            'model': browser.evaluate('document.querySelector("#model-picker")?.value??null'),
            'reading': browser.evaluate('(()=>{const e=document.querySelector(".conversation");return e?{top:e.scrollTop,left:e.scrollLeft}:null})()')}


def compare_context(before, after, *, reading_tolerance=1):
    fields = ('view', 'draft', 'storage', 'prompt', 'model')
    checks = {key + '_preserved': before[key] == after[key] for key in fields}
    if before['reading'] is None or after['reading'] is None:
        checks['reading_position_preserved'] = before['reading'] == after['reading']
    else:
        checks['reading_position_preserved'] = all(abs(before['reading'][key] - after['reading'][key]) <= reading_tolerance for key in ('top', 'left'))
    return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
            'before_context_sha256': fingerprint(before), 'after_context_sha256': fingerprint(after),
            'draft_text_exported': False, 'storage_values_exported': False}


@contextmanager
def browser_zoom_200(review):
    """Actual native browser accelerators, independent readback and restoration.

    The root still owns outer cleanup. This helper never changes device metrics,
    page scale, CSS zoom, display settings or protected configuration.
    """
    from scripts.probe_v5_shell import native_zoom_key
    from workspace import launcher
    review.close()
    review._guard()
    initial = viewport(review.b)
    record = {'kind': 'native_browser_200_percent', 'status': 'IN_PROGRESS', 'initial': initial,
              'method': 'Existing native XTEST Ctrl+0/Ctrl+equal browser accelerators; fresh native pointer calibration after scale changes.',
              'physical_keyboard': 'UNVERIFIED; synthesized native events are not a physical keyboard test.'}
    review.rows.append(record)
    baseline = None

    def go_to(factor):
        nonlocal baseline
        native_zoom_key(review.b, launcher, '0')
        base = viewport(review.b)
        if baseline is None:
            baseline = base
        for _ in range(14):
            value = viewport(review.b)
            ratio = value['dpr'] / base['dpr']
            if abs(ratio - factor) <= .025:
                # Finish the native browser accelerator UI before measuring
                # page pointer regions. Browser chrome may consume Escape.
                native_key(review.b, 'Escape', wait_for_dom=False)
                return base, value
            native_zoom_key(review.b, launcher, 'equal' if ratio < factor else 'minus')
        raise RuntimeError('native_browser_zoom_factor_not_reachable')

    try:
        review.qualified_geometry = None
        baseline, doubled = go_to(2)
        require(abs(doubled['dpr'] / baseline['dpr'] - 2) <= .025
                and abs(doubled['innerWidth'] * 2 - baseline['innerWidth']) <= 4
                and abs(doubled['innerHeight'] * 2 - baseline['innerHeight']) <= 4
                and doubled['visual_scale'] == baseline['visual_scale'] == 1
                and doubled['css_zoom'] == baseline['css_zoom'], 'native_200_percent_readbacks_not_independently_verified')
        record.update(baseline_100=baseline, actual_200=doubled, native_pointer=review.fresh_native())
        yield record
        record['status'] = 'PASS'
    except BaseException:
        record['status'] = 'FAIL'
        raise
    finally:
        # Escape uses the exact focused owned pin; never create a replacement
        # profile/document. Outer cleanup must retain any restoration failure.
        try:
            if baseline is not None:
                review.close()
                _base, restored = go_to(initial['dpr'] / baseline['dpr'])
                require(abs(restored['dpr'] - initial['dpr']) <= .025
                        and abs(restored['innerWidth'] - initial['innerWidth']) <= 2,
                        'initial_native_browser_zoom_not_restored')
                record['restored'] = restored
                record['restore_status'] = 'PASS'
                try:
                    record['restored_native_pointer'] = review.fresh_native()
                except BaseException:
                    record['restore_pointer_diagnostics'] = getattr(review.b, '_native_diagnostics', {})
                    raise
            else:
                record['restore_status'] = 'UNVERIFIED_BEFORE_BASELINE'
        except BaseException:
            record['restore_status'] = 'FAIL'
            record['status'] = 'FAIL'
            raise


class SurfaceReview:
    def __init__(self, browser, *, case, rpc_read, requalify, capture=None):
        require(browser.identity.get('url') == ORIGIN and browser.identity.get('catalog') == 'production'
                and browser.identity.get('isolated_server') is False, 'actual_existing_production_pin_required')
        self.b, self.rpc, self.qualify, self.capture = browser, rpc_read, requalify, capture
        self.viewed, self.target = owns_case(case, rpc_read('session.list', {}))
        require(rpc_read('view.read', {}).get('session_id') == self.viewed, 'select_owned_A_before_geometry_review')
        self.rows = []
        self.qualified_geometry = None
        self.b.evaluate('''(()=>{if(window.__v6SurfaceKeyReview)return;
          const state={sequence:0,expected:null};window.__v6SurfaceKeyReview=state;
          addEventListener('keydown',event=>{if(event.isTrusted&&event.key===state.expected)state.sequence++},true)})()''')

    def fresh_native(self):
        """Caller retires old mapping, closes overlays, rechecks actual window."""
        proof = self.qualify()
        require(proof.get('status') == 'PASS' and getattr(self.b, '_native_coordinates', None), 'native_geometry_not_qualified')
        self.qualified_geometry = self._geometry_key()
        return proof

    def _geometry_key(self):
        value = viewport(self.b)
        return tuple(value[key] for key in ('left', 'top', 'width', 'height', 'innerWidth', 'innerHeight', 'dpr', 'visual_scale', 'css_zoom'))

    def _guard(self):
        require(self.qualified_geometry == self._geometry_key(), 'requalify_after_window_or_browser_zoom_change')
        require(self.rpc('view.read', {}).get('session_id') == self.viewed, 'geometry_must_not_switch_A_to_managed_B')

    def click(self, selector):
        self._guard()
        require_owned_native_focus(self.b)
        self.b.click(selector)

    def click_visible_outside(self, selector):
        self._guard()
        require_owned_native_focus(self.b)
        point = self.b.evaluate('''(()=>{const e=document.querySelector(''' + json.dumps(selector) + ''');
          if(!e)return null;const r=e.getBoundingClientRect();
          for(const u of [.5,.1,.9,.02,.98])for(const v of [.5,.1,.9]){
            const x=r.x+r.width*u,y=r.y+r.height*v,hit=document.elementFromPoint(x,y);
            if(hit&&(hit===e||e.contains(hit)))return {x,y}}
          return null})()''')
        require(point is not None, 'outside_control_has_no_visible_hit_point')
        self.b.mouse(point['x'], point['y'])
        return point

    def key(self, key, shift=False):
        self._guard()
        native_key(self.b, key, shift=shift)

    def settle(self):
        # Finite rAF stabilization observes the real entry; it neither pauses
        # animation nor fabricates a component state. Motion review is separate.
        self.b.evaluate('''(async()=>{let old=null,n=0;const until=performance.now()+2000;
        while(performance.now()<until){await new Promise(requestAnimationFrame);const all=[...document.querySelectorAll("dialog[open],.anchored-popover")];
          const v=all.map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height,getComputedStyle(e).opacity]});
          n=old&&JSON.stringify(old)===JSON.stringify(v)?n+1:0;old=v;if(n>=4)return true}
        throw Error("bounded_surface_did_not_settle")})()''')

    def close(self):
        for _ in range(3):
            if not self.b.evaluate('!!document.querySelector("dialog[open],.anchored-popover")'):
                return
            self.key('Escape')
            self.settle()
        require(not self.b.evaluate('!!document.querySelector("dialog[open],.anchored-popover")'), 'owned_overlay_survived_three_Escapes')

    def focused(self):
        return self.b.evaluate('''(()=>{const e=document.activeElement;return {tag:e?.tagName,id:e?.id??null,
          role:e?.getAttribute("role"),inside_open_dialog:!!e?.closest("dialog[open]"),inside_popover:!!e?.closest(".anchored-popover")}})()''')

    @recorded
    def popover(self, trigger, surface, *, menu=True, outside='#prompt'):
        """Only opens/closes real controls. Does not invoke upload/search/run."""
        self.close()
        before_context = capture_context(self.b, self.rpc)
        before = self.b.rect(trigger)
        self.click(trigger)
        self.b.wait('!!document.querySelector(' + json.dumps(surface) + ')')
        self.settle()
        after, panel, view = self.b.rect(trigger), self.b.rect(surface), viewport(self.b)
        assessment = assess_popover(before, after, panel, view)
        self.rows[-1].update(trigger=trigger, surface=surface, before=before, after=after,
                             surface_rect=panel, viewport=view, geometry=assessment)
        require(assessment['status'] == 'PASS', ';'.join(assessment['failures']))
        self.b.wait('document.querySelector(' + json.dumps(surface) + ').contains(document.activeElement)')
        keyboard = []
        if menu:
            items = self.b.evaluate('[...document.querySelector(' + json.dumps(surface) + ').querySelectorAll(\'[role="menuitem"]\')].filter(e=>!e.disabled).map(e=>e.textContent.trim())')
            require(bool(items), 'real_menu_has_no_enabled_items')
            for key, expected in (('End', len(items)-1), ('Home', 0), ('Up', len(items)-1), ('Down', 0)):
                self.key(key)
                index = self.b.evaluate('[...document.querySelector(' + json.dumps(surface) + ').querySelectorAll(\'[role="menuitem"]\')].filter(e=>!e.disabled).indexOf(document.activeElement)')
                require(index == expected, 'native_menu_navigation_did_not_skip_disabled_or_wrap')
                keyboard.append({'key': key, 'enabled_item_index': index})
            # Exercise real typeahead only when its first character is unique.
            unique = next(((index, text[0].lower()) for index, text in enumerate(items) if text and re.fullmatch('[a-z]', text[0].lower())
                           and sum(other.lower().startswith(text[0].lower()) for other in items) == 1), None)
            if unique:
                self.key(unique[1])
                index = self.b.evaluate('[...document.querySelector(' + json.dumps(surface) + ').querySelectorAll(\'[role="menuitem"]\')].filter(e=>!e.disabled).indexOf(document.activeElement)')
                require(index == unique[0], 'native_menu_typeahead_wrong_item')
                keyboard.append({'key': 'unique-letter-typeahead', 'enabled_item_index': index})
        if self.capture:
            self.capture('popover-' + surface.lstrip('#'), surface)
        self.key('Escape')
        self.b.wait('!document.querySelector(' + json.dumps(surface) + ')')
        require(self.b.evaluate('document.activeElement===document.querySelector(' + json.dumps(trigger) + ')'), 'Escape_did_not_restore_originating_trigger')
        for key in ('Return', 'space'):
            self.key(key)
            self.b.wait('!!document.querySelector(' + json.dumps(surface) + ')')
            self.key('Escape')
            self.b.wait('!document.querySelector(' + json.dumps(surface) + ')')
            require(self.b.evaluate('document.activeElement===document.querySelector(' + json.dumps(trigger) + ')'), 'keyboard_reopen_lost_trigger_focus')
            keyboard.append({'key': key, 'opens_real_control': True, 'Escape_returns_trigger': True})
        # Outside pointer dismissal must leave focus on the clicked textarea.
        self.click(trigger)
        self.b.wait('!!document.querySelector(' + json.dumps(surface) + ')')
        outside_point = self.click_visible_outside(outside)
        self.b.wait('!document.querySelector(' + json.dumps(surface) + ')')
        require(self.b.evaluate('document.activeElement===document.querySelector(' + json.dumps(outside) + ')'), 'outside_click_focus_was_stolen')
        if menu:
            for shift in (False, True):
                self.click(trigger)
                self.b.wait('!!document.querySelector(' + json.dumps(surface) + ')')
                self.key('Tab', shift)
                self.b.wait('!document.querySelector(' + json.dumps(surface) + ')')
                focused = self.focused()
                require(focused['tag'] not in ('BODY', 'HTML') and not focused['inside_popover'], 'menu_Tab_left_unusable_focus')
                keyboard.append({'key': 'Shift+Tab' if shift else 'Tab', 'focus': focused})
        preservation = compare_context(before_context, capture_context(self.b, self.rpc))
        require(preservation['status'] == 'PASS', 'popover_changed_A_draft_view_model_selection_or_scroll')
        result = {'kind': 'popover', 'trigger': trigger, 'surface': surface, 'viewport': view,
                  'before': before, 'after': after, 'surface_rect': panel, 'geometry': assessment,
                  'native_navigation': keyboard, 'Escape_focus_return': True, 'outside_focus_preserved': True,
                  'outside_native_click_point': outside_point,
                  'preservation': preservation, 'smoothness': 'Not established by this geometry check.'}
        return result

    @recorded
    def modal_opened(self, label, *, return_selector, focused_form=False):
        """Call after real Settings/owned-B menu action; saves no edits/deletes."""
        selector = 'dialog[open][aria-label=' + json.dumps(label) + ']'
        self.b.wait('!!document.querySelector(' + json.dumps(selector) + ')')
        self.settle()
        value = self.b.evaluate('''(()=>{const d=document.querySelector(''' + json.dumps(selector) + ''');
          const targets=[...d.querySelectorAll('button,input,textarea,select,a[href],[tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length);
          return {native_modal:d.matches(':modal'),surface:d.dataset.surface,rect:d.getBoundingClientRect().toJSON(),
            focus_inside:d.contains(document.activeElement),focused_tag:document.activeElement?.tagName,
            focused_form:document.activeElement?.matches('input:not([type=checkbox]):not([type=radio]),textarea'),focusable_count:targets.length}})()''')
        self.rows[-1].update(label=label, **value)
        require(value['native_modal'] and value['focus_inside'], 'dialog_is_not_native_modal_or_initial_focus_is_outside')
        if focused_form:
            require(value['focused_form'], 'focused_edit_form_did_not_start_on_input')
        require(0 < value['focusable_count'] <= 96, 'bounded_modal_focus_inventory_required')
        focus_trace = []
        for shift, count in ((False, value['focusable_count'] + 2), (True, 3)):
            for _ in range(count):
                self.key('Tab', shift)
                focus = self.focused()
                require(focus['inside_open_dialog'], 'native_modal_Tab_escaped_to_background')
                focus_trace.append({'shift': shift, **focus})
        # Native modal implicit inertness need not appear as an inert attribute.
        # An actual focus() attempt is blocked by the browser's native modal.
        blocked_focus = self.b.evaluate('''(()=>{document.querySelector('#prompt')?.focus();
          return document.querySelector(''' + json.dumps(selector) + ''').contains(document.activeElement)})()''')
        require(blocked_focus, 'native_modal_background_not_inert_to_focus')
        if self.capture:
            self.capture('modal-' + re.sub('[^a-z0-9]+', '-', label.lower()), selector)
        self.key('Escape')
        self.b.wait('!document.querySelector("dialog[open]")')
        require(self.b.evaluate('document.activeElement===document.querySelector(' + json.dumps(return_selector) + ')'), 'modal_Escape_did_not_restore_logical_invoker')
        result = {'kind': 'modal', 'label': label, **value, 'focus_trace': focus_trace,
                  'background_focus_attempt_blocked': blocked_focus, 'Escape_return': return_selector,
                  'input_scope': 'Native synthesized XTEST Tab/Escape; explicit DOM focus attempt tests browser implicit inertness.'}
        return result

    @recorded
    def sheets(self):
        """Alternate actual Files/Details; small modal fallback is explicit."""
        self.close()
        before_context = capture_context(self.b, self.rpc)
        results = []
        self.rows[-1]['samples'] = results
        for label, trigger in (('Files', '#files-toggle'), ('Details', '#diagnostics'), ('Files', '#files-toggle')):
            if self.b.evaluate('!!document.querySelector("dialog:modal")'):
                self.key('Escape')
                self.b.wait('!document.querySelector("dialog[open]")')
            self.click(trigger)
            selector = 'dialog[open][aria-label=' + json.dumps(label) + ']'
            self.b.wait('!!document.querySelector(' + json.dumps(selector) + ')')
            self.settle()
            value = self.b.evaluate('''(()=>{const d=document.querySelector('dialog[open]'),c=document.querySelector('.composer-area');
              const box=e=>e?.getBoundingClientRect().toJSON()??null;const hit=e=>{if(!e)return null;const r=e.getBoundingClientRect();
                const p=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {rect:box(e),visible:r.width>0&&r.height>0,hit:!!p&&(e===p||e.contains(p))}};
              return {label:d.getAttribute('aria-label'),open_count:document.querySelectorAll('dialog[open]').length,
                native_modal:d.matches(':modal'),surface:d.dataset.surface,panel:box(d),composer:box(c),
                send_or_cancel:hit(document.querySelector('#cancel-response,#send')),
                readiness:hit(document.querySelector('.readiness-banner')),
                errors:[...document.querySelectorAll('.composer-area .error-banner,.composer-area .run-error')].map(hit),
                accessible_readiness:{present:!!document.querySelector('#model-readiness'),
                  live:document.querySelector('#model-readiness')?.getAttribute('aria-live'),
                  screen_reader_only:document.querySelector('#model-readiness')?.classList.contains('sr-only')},
                prompt:hit(document.querySelector('#prompt'))}})()''')
            value['viewport'] = viewport(self.b)
            results.append(value)
            require(value['label'] == label and value['open_count'] == 1, 'alternating_sheets_left_old_panel_or_backdrop')
            if value['surface'] == 'sheet':
                require(not value['native_modal'], 'desktop_sheet_accidentally_modal')
                require(value['composer'] and rect_edges(value['panel'])['bottom'] <= rect_edges(value['composer'])['top'] - 7.5,
                        'desktop_sheet_did_not_reserve_actual_composer_area')
                require(value['send_or_cancel'] and value['send_or_cancel']['hit'], 'sheet_covers_Send_or_Cancel')
                require(value['prompt'] and value['prompt']['hit'], 'sheet_covers_composer_input')
                if value['readiness'] and value['readiness']['visible']:
                    require(value['readiness']['hit'], 'sheet_covers_readiness_or_error_status')
                require(all(not item['visible'] or item['hit'] for item in value['errors']), 'sheet_covers_visible_composer_error')
                value['mode'] = 'nonmodal_sheet'
            else:
                require(value['native_modal'], 'small_surface_neither_useful_sheet_nor_focused_modal')
                self.b.wait('document.querySelector("dialog:modal").contains(document.activeElement)')
                value['mode'] = 'explicit_focused_modal_fallback'
            if self.capture:
                self.capture('surface-' + label.lower(), 'dialog[open]')
        if results[-1]['mode'] == 'nonmodal_sheet':
            self.click('#prompt')
            self.b.wait('!document.querySelector("dialog[open]")')
            require(self.b.evaluate('document.activeElement===document.querySelector("#prompt")'), 'sheet_outside_click_stole_new_input_focus')
        else:
            self.close()
            require(self.b.evaluate('document.activeElement===document.querySelector("#files-toggle")'), 'small_modal_Escape_lost_Files_invoker')
        preservation = compare_context(before_context, capture_context(self.b, self.rpc))
        require(preservation['status'] == 'PASS', 'surface_switching_changed_A_draft_view_or_scroll')
        result = {'kind': 'surface_alternation', 'samples': results, 'preservation': preservation,
                  'true_background_input_blocking_when_modal': 'Use modal_opened() separately for full focus-cycle proof.'}
        return result

    @recorded
    def owned_management_modal(self, *, deletion_review=False):
        """Open B's actual rename/deletion REVIEW; never submit or confirm."""
        self.close()
        before = capture_context(self.b, self.rpc)
        trigger = '#conversation-options-' + self.target
        self.click(trigger)
        self.b.wait('!!document.querySelector("#row-actions")')
        self.key('End' if deletion_review else 'Home')
        self.key('Return')
        label = 'Delete conversation' if deletion_review else 'Conversation'
        result = self.modal_opened(label, return_selector=trigger, focused_form=not deletion_review)
        preservation = compare_context(before, capture_context(self.b, self.rpc))
        require(preservation['status'] == 'PASS', 'managing_B_changed_A_view_or_unsent_draft')
        result['management_target_ID'] = self.target
        result['viewed_ID'] = self.viewed
        result['preservation'] = preservation
        result['mutation_submitted'] = False
        return result
