"""One zoom-restore observation; native metadata, no screenshots/focus forcing.

Read and apply $reference-led-design. Caller supplies the one exclusively owned
ProductionPin. No view/catalog writes, browser flags, timeout changes or matrix.
"""
import ctypes as c
import ctypes.util
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

SETTLE_OBSERVATION_SECONDS = 2.0
POINT_EVENT_SECONDS = .4
SOURCE_FILES = ('scripts/probe_v4_chat.py', 'scripts/probe_v4_visual.py', 'scripts/probe_v5_shell.py',
                'scripts/v6_surface_review.py', 'workspace/capture.py', 'workspace/launcher.py',
                'workspace/frontend/src/main.tsx', 'workspace/frontend/src/controls.tsx',
                'workspace/frontend/src/AnchoredPopover.tsx', 'workspace/frontend/src/interaction-surfaces.css',
                'workspace/frontend/src/style.css', 'workspace/ui/dist/identities.json',
                'workspace/ui/dist/app.js', 'workspace/ui/dist/app.css')


def require(value, code):
    if not value:
        raise RuntimeError(code)


def command(*args):
    return json.loads(subprocess.check_output(args, text=True, timeout=4))


def active_owned(browser, expected_address=None):
    from workspace import launcher
    active = command('/usr/bin/hyprctl', 'activewindow', '-j')
    require(active.get('class') == 'HermesWorkspace' and launcher.owns_browser(active.get('pid', 0)),
            'native_focus_displaced_abort_without_refocus')
    require(expected_address is None or active.get('address') == expected_address, 'different_owned_window_abort_without_refocus')
    rows = [row for row in command('/usr/bin/hyprctl', 'clients', '-j') if row.get('address') == active.get('address')]
    require(len(rows) == 1 and launcher.owns_browser(rows[0].get('pid', 0)), 'same_exact_owned_native_surface_required')
    return rows[0]


def contains(rect, point):
    return rect[0] <= point[0] < rect[0] + rect[2] and rect[1] <= point[1] < rect[1] + rect[3]


class NativeMetadata:
    """Export only XRes-owned resource metadata; never read titles or pixels."""
    def __init__(self):
        from workspace.capture import owned_x11_window
        display = os.environ.get('DISPLAY', '')
        require(re.fullmatch(r':\d+(?:\.\d+)?', display), 'local_X_display_required')
        self.main, _display = owned_x11_window()
        library = ctypes.util.find_library('X11')
        require(library, 'installed_Xlib_required')
        self.x = c.CDLL(library)
        self.x.XOpenDisplay.argtypes = [c.c_char_p]; self.x.XOpenDisplay.restype = c.c_void_p
        self.x.XCloseDisplay.argtypes = [c.c_void_p]
        self.x.XDefaultRootWindow.argtypes = [c.c_void_p]; self.x.XDefaultRootWindow.restype = c.c_ulong
        self.x.XFree.argtypes = [c.c_void_p]
        self.x.XQueryTree.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong), c.POINTER(c.c_ulong), c.POINTER(c.POINTER(c.c_ulong)), c.POINTER(c.c_uint)]
        self.x.XTranslateCoordinates.argtypes = [c.c_void_p, c.c_ulong, c.c_ulong, c.c_int, c.c_int, c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_ulong)]
        self.x.XGetTransientForHint.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong)]
        self.x.XQueryPointer.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong), c.POINTER(c.c_ulong), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_uint)]
        self.x.XGetInputFocus.argtypes = [c.c_void_p, c.POINTER(c.c_ulong), c.POINTER(c.c_int)]
        class Attributes(c.Structure):
            _fields_ = [('x', c.c_int), ('y', c.c_int), ('width', c.c_int), ('height', c.c_int),
                        ('border_width', c.c_int), ('depth', c.c_int), ('visual', c.c_void_p), ('root', c.c_ulong),
                        ('class_', c.c_int), ('bit_gravity', c.c_int), ('win_gravity', c.c_int), ('backing_store', c.c_int),
                        ('backing_planes', c.c_ulong), ('backing_pixel', c.c_ulong), ('save_under', c.c_int),
                        ('colormap', c.c_ulong), ('map_installed', c.c_int), ('map_state', c.c_int),
                        ('all_event_masks', c.c_long), ('your_event_mask', c.c_long), ('do_not_propagate_mask', c.c_long),
                        ('override_redirect', c.c_int), ('screen', c.c_void_p)]
        self.Attributes = Attributes
        self.x.XGetWindowAttributes.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(Attributes)]
        handler_type = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_void_p)
        self.handler = handler_type(lambda _display, _error: 0)
        self.x.XSetErrorHandler.argtypes = [c.c_void_p]; self.x.XSetErrorHandler.restype = c.c_void_p
        self.previous = self.x.XSetErrorHandler(c.cast(self.handler, c.c_void_p))
        self.display = self.x.XOpenDisplay(display.encode())
        if not self.display:
            self.x.XSetErrorHandler(self.previous)
            raise RuntimeError('readonly_X_display_connection_failed')
        self.root = self.x.XDefaultRootWindow(self.display)
        self.display_name, self.first_seen = display, {}

    def close(self):
        self.x.XCloseDisplay(self.display)
        self.x.XSetErrorHandler(self.previous)

    def children(self, window):
        root, parent, array, count = c.c_ulong(), c.c_ulong(), c.POINTER(c.c_ulong)(), c.c_uint()
        try:
            if not self.x.XQueryTree(self.display, window, c.byref(root), c.byref(parent), c.byref(array), c.byref(count)):
                return []
            require(count.value <= 512, 'bounded_native_tree_required')
            return [int(array[index]) for index in range(count.value)]
        finally:
            if array:
                self.x.XFree(array)

    def snapshot(self, target):
        from workspace import launcher
        from workspace.capture import x11_server_pid
        now, rows = time.monotonic(), []
        candidates = set(self.children(self.root) + self.children(self.main) + [self.main])
        for xid in sorted(candidates):
            attrs = self.Attributes()
            if not self.x.XGetWindowAttributes(self.display, xid, c.byref(attrs)) or attrs.map_state != 2:
                continue
            try:
                pid = x11_server_pid(xid, self.display_name)
            except RuntimeError:
                continue
            if not launcher.owns_browser(pid):
                continue
            x, y, child = c.c_int(), c.c_int(), c.c_ulong()
            if not self.x.XTranslateCoordinates(self.display, xid, self.root, 0, 0, c.byref(x), c.byref(y), c.byref(child)):
                continue
            transient = c.c_ulong()
            hinted = self.x.XGetTransientForHint(self.display, xid, c.byref(transient))
            rect = [x.value, y.value, attrs.width, attrs.height]
            self.first_seen.setdefault(xid, now)
            rows.append({'xid': hex(xid), 'main_app_window': xid == self.main, 'XRes_profile_ownership': True,
                         'rect_native': rect, 'override_redirect': bool(attrs.override_redirect),
                         'transient_for_main': bool(hinted and transient.value == self.main),
                         'covers_estimated_Settings_point': contains(rect, target),
                         'first_observed_viewable_ago_ms': (now - self.first_seen[xid]) * 1000})
        root, child, rx, ry, wx, wy, mask = c.c_ulong(), c.c_ulong(), c.c_int(), c.c_int(), c.c_int(), c.c_int(), c.c_uint()
        valid = self.x.XQueryPointer(self.display, self.root, c.byref(root), c.byref(child), c.byref(rx), c.byref(ry), c.byref(wx), c.byref(wy), c.byref(mask))
        focus, revert = c.c_ulong(), c.c_int()
        self.x.XGetInputFocus(self.display, c.byref(focus), c.byref(revert))
        known = {int(row['xid'], 16) for row in rows}
        return {'owned_viewable_windows': rows, 'main_xid': hex(self.main),
                'pointer_native': [rx.value, ry.value] if valid else None,
                'pointer_child': hex(child.value) if child.value in known else 'unowned_or_unresolved',
                'input_focus': hex(focus.value) if focus.value in known else 'unowned_or_unresolved',
                'age_scope': 'Time since first read-only observation of this viewable owned XID, not native creation age or proof of uninterrupted mapping.',
                'semantic_zoom_popup_identity': 'UNPROVEN: native resource ownership/geometry is not a named Chromium Views widget.'}


def point_observation(browser, native, gx, gy, expected_address):
    active_owned(browser, expected_address)
    before = browser.evaluate('window.__v4pointerSequence')
    native.move(gx, gy)
    until = time.monotonic() + POINT_EVENT_SECONDS
    while True:
        event = browser.evaluate('window.__v4pointer')
        cursor = command('/usr/bin/hyprctl', 'cursorpos', '-j')
        fresh = bool(event and event['sequence'] > before and event['trusted'])
        matched = abs(cursor['x'] - gx) <= 1 and abs(cursor['y'] - gy) <= 1
        if fresh and matched or time.monotonic() >= until:
            return {'requested_native': [gx, gy], 'cursor': cursor, 'event': event, 'fresh_DOM_event': fresh, 'cursor_matches': matched}
        time.sleep(.02)


def qualify_points_once(browser, native, client):
    """Exactly two fixed body pairs and one nine-point pass; no clicks/retry."""
    pairs, samples = [], []
    for _ in range(2):
        pair = []
        for u, v in ((.4, .3), (.55, .5)):
            gx, gy = client['at'][0] + round(client['size'][0] * u), client['at'][1] + round(client['size'][1] * v)
            result = point_observation(browser, native, gx, gy, client['address']); samples.append(result)
            if not result['fresh_DOM_event'] or not result['cursor_matches']:
                return {'status': 'FAIL_BODY_EVENT', 'body_samples': samples, 'qualification_attempts': 1}
            pair.append((gx, gy, result['event']))
        a, b = pair
        dx, dy = b[2]['x'] - a[2]['x'], b[2]['y'] - a[2]['y']
        require(dx and dy, 'nondegenerate_body_coordinates_required')
        sx, sy = (b[0] - a[0]) / dx, (b[1] - a[1]) / dy
        pairs.append([sx, sy, a[0] - a[2]['x'] * sx, a[1] - a[2]['y'] * sy])
    require(all(math.isfinite(v) for pair in pairs for v in pair) and max(abs(a - b) for a, b in zip(*pairs)) <= 1,
            'one_fixed_pair_requalification_not_stable')
    sx, sy, ox, oy = pairs[-1]
    require(0 < sx < 8 and 0 < sy < 8, 'bounded_positive_native_mapping_required')
    points = []; rect = browser.rect('#settings-toggle')
    for u in (.25, .5, .75):
        for v in (.25, .5, .75):
            x, y = rect['x'] + rect['width'] * u, rect['y'] + rect['height'] * v
            gx, gy = round(ox + x * sx), round(oy + y * sy)
            require(contains([*client['at'], *client['size']], [gx, gy]), 'mapped_point_must_remain_inside_original_app')
            result = point_observation(browser, native, gx, gy, client['address'])
            error = max(abs(result['event']['x'] - x), abs(result['event']['y'] - y)) if result['fresh_DOM_event'] else None
            points.append({'u': u, 'v': v, 'observation': result, 'fresh_event_CSS_error': error})
            if not result['fresh_DOM_event'] or not result['cursor_matches'] or result['event']['target'] != 'settings-toggle' or error > 1.5:
                return {'status': 'FAIL_SETTINGS_POINT', 'body_samples': samples, 'nine_points': points, 'qualification_attempts': 1}
    return {'status': 'PASS_POINTS_ONLY', 'body_samples': samples, 'nine_points': points, 'mapping': pairs[-1],
            'qualification_attempts': 1, 'clicks_or_settings_changes': False, 'scope': 'Fresh native point delivery only, not all18 functional subchecks or human input approval.'}


def observe_restore(browser, output, app_root):
    """Start at proven100%; one200→100 cycle,2s observation,one point pass."""
    from scripts.probe_v4_chat import rpc
    from scripts.probe_v4_visual import NativeX11Input
    from scripts.probe_v5_shell import native_zoom_key
    from scripts.v6_surface_review import capture_context, compare_context, viewport
    from workspace import launcher
    output, app_root = Path(output), Path(app_root).resolve(strict=True)
    require(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)), 'new_regular_diagnostic_path_required')
    parent = output.parent.stat()
    require(output.parent.is_dir() and parent.st_uid == os.getuid() and parent.st_mode & 0o077 == 0,
            'existing_private_operator_output_directory_required')
    source_before = {name: hashlib.sha256((app_root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
    require(browser.identity.get('catalog') == 'production' and browser.identity.get('isolated_server') is False,
            'actual_existing_pin_required')
    require(not browser.evaluate('!!document.querySelector("dialog[open],.anchored-popover,#cancel-response,.recording-indicator")||!!document.pointerLockElement'),
            'preserve_active_original_state_no_diagnostic')
    require(browser.evaluate('Number.isInteger(window.__v4pointerSequence)'), 'existing_pointer_observer_required')
    client = active_owned(browser)
    before = capture_context(browser, lambda m, f: rpc(browser, m, f))
    original = viewport(browser)
    monitor = next(row for row in command('/usr/bin/hyprctl', 'monitors', '-j') if row['id'] == client['monitor'])
    require(original['visual_scale'] == 1 and original['css_zoom'] == '1'
            and abs(original['dpr'] - monitor['scale']) < .025 and abs(original['innerWidth'] - client['size'][0]) <= 1,
            'begin_with_independently_consistent_native100percent')
    report = {'status': 'IN_PROGRESS', 'browser': browser.pipe.call('Browser.getVersion'), 'original': original,
              'diagnostic_helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'source_sha256_before': source_before,
              'scope': 'One200→100 native zoom cycle; read-only owned native resource metadata; no screenshot, view/data write, focus forcing or full matrix.',
              'observations': [], 'same_point_deadline_seconds': POINT_EVENT_SECONDS, 'natural_observation_seconds': SETTLE_OBSERVATION_SECONDS}
    old_native = getattr(browser, '_native_input', None)
    native = None
    metadata = None; original_cursor = command('/usr/bin/hyprctl', 'cursorpos', '-j')
    def snapshot(label):
        current = viewport(browser)
        rect = browser.rect('#settings-toggle')
        target = [round(client['at'][0] + (rect['x'] + rect['width'] * .25) * client['size'][0] / current['innerWidth']),
                  round(client['at'][1] + (rect['y'] + rect['height'] * .25) * client['size'][1] / current['innerHeight'])]
        page = browser.evaluate('''(()=>{const e=document.querySelector('#settings-toggle'),r=e.getBoundingClientRect(),h=document.elementFromPoint(r.x+r.width*.25,r.y+r.height*.25);
          return {rect:r.toJSON(),hit_button_id:h?.closest('button')?.id??null,pointer_events:getComputedStyle(e).pointerEvents,
            document_focused:document.hasFocus(),active_id:document.activeElement?.id??null,latest_pointer:window.__v4pointer}})()''')
        try:
            active_owned(browser, client['address']); native_focus = 'ORIGINAL_OWNED_APP'
        except RuntimeError:
            native_focus = 'DISPLACED_NO_REFOCUS'
        report['observations'].append({'stage': label, 'wall_monotonic': time.monotonic(), 'viewport': current,
                                       'page': page, 'native_focus': native_focus, 'native': metadata.snapshot(target)})
    try:
        native = old_native or NativeX11Input(); browser._native_input = native
        metadata = NativeMetadata(); snapshot('before_zoom')
        for _ in range(8):
            if abs(viewport(browser)['dpr'] / original['dpr'] - 2) <= .025:
                break
            active_owned(browser, client['address']); native_zoom_key(browser, launcher, 'equal')
        doubled = viewport(browser)
        require(abs(doubled['dpr'] / original['dpr'] - 2) <= .025 and abs(doubled['innerWidth'] * 2 - original['innerWidth']) <= 4,
                'actual_native200percent_not_reached')
        snapshot('at_200_percent_no_functional_repeats')
        active_owned(browser, client['address']); native_zoom_key(browser, launcher, '0')
        require(abs(viewport(browser)['dpr'] - original['dpr']) <= .025, 'native100percent_not_restored')
        snapshot('immediately_after_Ctrl0')
        # Park in the already-proven body calibration area, outside the suspected
        # upper-right chrome bubble. No click, key dismissal or focus transfer.
        active_owned(browser, client['address'])
        native.move(client['at'][0] + round(client['size'][0] * .55), client['at'][1] + round(client['size'][1] * .5))
        settle_started = time.monotonic(); until = settle_started + SETTLE_OBSERVATION_SECONDS
        while time.monotonic() < until:
            snapshot('natural_settle_observation'); time.sleep(.1)
            active_owned(browser, client['address'])
        report['actual_observation_seconds'] = time.monotonic() - settle_started
        report['point_requalification'] = qualify_points_once(browser, native, client)
        snapshot('after_single_point_requalification')
        report['status'] = 'OBSERVED_ONLY'
    except Exception as error:
        code = str(error)
        report.update(status='FAIL', error_category=type(error).__name__, error_code=code if re.fullmatch('[A-Za-z0-9_]{1,180}', code) else 'readonly_diagnostic_error')
        raise
    finally:
        report['cleanup'] = {}
        def cleanup(name, callback):
            try:
                callback(); report['cleanup'][name] = {'status': 'ok'}
            except Exception as error:
                report['cleanup'][name] = {'status': 'failed', 'error_category': type(error).__name__}; report['status'] = 'FAIL'
        def restore_zoom_if_needed():
            if abs(viewport(browser)['dpr'] - original['dpr']) > .025:
                active_owned(browser, client['address']); native_zoom_key(browser, launcher, '0')
                require(abs(viewport(browser)['dpr'] - original['dpr']) <= .025, 'original_zoom_not_recovered')
        cleanup('original_zoom', restore_zoom_if_needed)
        def restore_reading_only_if_context_unchanged():
            after = capture_context(browser, lambda m, f: rpc(browser, m, f))
            # Restore only a reflow-clamped scroll in the exact unchanged context.
            require(all(before[key] == after[key] for key in ('view', 'draft', 'storage', 'prompt', 'model')), 'original_data_changed_preserve_newer_state')
            if before['reading'] is not None:
                require(browser.evaluate('!!document.querySelector(".conversation")'), 'original_reading_surface_missing')
                browser.evaluate('(()=>{const e=document.querySelector(".conversation");e.scrollTop=' + json.dumps(before['reading']['top']) + ';e.scrollLeft=' + json.dumps(before['reading']['left']) + '})()')
            report['original_context'] = compare_context(before, capture_context(browser, lambda m, f: rpc(browser, m, f)))
            require(report['original_context']['status'] == 'PASS', 'original_context_not_restored')
        cleanup('original_context', restore_reading_only_if_context_unchanged)
        if native:
            cleanup('cursor', lambda: (active_owned(browser, client['address']), native.move(original_cursor['x'], original_cursor['y'])))
        if metadata:
            cleanup('readonly_X_connection', metadata.close)
        if old_native is None and native:
            cleanup('own_native_connection', native.close); browser._native_input = None
        def unchanged_sources():
            report['source_sha256_after'] = {name: hashlib.sha256((app_root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
            report['source_unchanged'] = source_before == report['source_sha256_after']
            require(report['source_unchanged'], 'diagnostic_sources_changed')
        cleanup('source_identity', unchanged_sources)
        with output.open('x') as stream:
            json.dump(report, stream, indent=2); stream.write('\n')
        output.chmod(0o600)
    return report
