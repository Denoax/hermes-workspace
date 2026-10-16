"""Observe production parenting, then type only into its exact owned chooser.

No window floating, focusing, rules, clipboard or API-based file selection. The
unchanged v5 assisted driver remains historical and is not imported as a driver.
"""
from __future__ import annotations

import ctypes as c
import ctypes.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from owned_native_picker import CAPTION, path_keys, process_identity


class ChooserWindowObservationError(RuntimeError):
    """Preserve filtered owned-window metadata while refusing ambiguous input."""
    def __init__(self, windows):
        super().__init__('native_chooser_X11_window_not_unique')
        self.observation = {'matching_viewable_owned_windows': len(windows),
                            'windows': windows}


def select_parented_window(windows, expected_parent):
    """KDE completion popups share the process/class but are not the chooser."""
    if type(expected_parent) is not int or expected_parent <= 0:
        raise RuntimeError('verified_Hermes_X11_parent_required')
    candidates = [row for row in windows if row.get('transient_for') == expected_parent]
    if len(candidates) != 1:
        raise ChooserWindowObservationError(candidates)
    return candidates[0]


def owned_chooser_x11(pid, display_name, expected_parent):
    """Read only XIDs/PIDs/classes/transient hints; never titles or pixels."""
    if type(pid) is not int or pid <= 0 or not re.fullmatch(r':\d+(?:\.\d+)?', display_name):
        raise RuntimeError('local_X11_chooser_metadata_required')
    from workspace.capture import x11_server_pid
    name = ctypes.util.find_library('X11')
    if not name:
        raise RuntimeError('native_chooser_Xlib_unavailable')
    x = c.CDLL(name)
    ptr, win, atom, integer, ulong = c.c_void_p, c.c_ulong, c.c_ulong, c.c_int, c.c_ulong
    x.XOpenDisplay.argtypes = [c.c_char_p]; x.XOpenDisplay.restype = ptr
    x.XCloseDisplay.argtypes = [ptr]
    x.XDefaultRootWindow.argtypes = [ptr]; x.XDefaultRootWindow.restype = win
    x.XInternAtom.argtypes = [ptr, c.c_char_p, integer]; x.XInternAtom.restype = atom
    x.XGetWindowProperty.argtypes = [ptr, win, atom, c.c_long, c.c_long, integer, atom,
        c.POINTER(atom), c.POINTER(integer), c.POINTER(ulong), c.POINTER(ulong), c.POINTER(ptr)]
    x.XQueryTree.argtypes = [ptr, win, c.POINTER(win), c.POINTER(win), c.POINTER(c.POINTER(win)), c.POINTER(c.c_uint)]
    x.XGetTransientForHint.argtypes = [ptr, win, c.POINTER(win)]
    x.XFree.argtypes = [ptr]
    class Attributes(c.Structure):
        _fields_ = [('x', integer), ('y', integer), ('width', integer), ('height', integer),
            ('border_width', integer), ('depth', integer), ('visual', ptr), ('root', win),
            ('class_', integer), ('bit_gravity', integer), ('win_gravity', integer), ('backing_store', integer),
            ('backing_planes', ulong), ('backing_pixel', ulong), ('save_under', integer), ('colormap', win),
            ('map_installed', integer), ('map_state', integer), ('all_event_masks', c.c_long),
            ('your_event_mask', c.c_long), ('do_not_propagate_mask', c.c_long),
            ('override_redirect', integer), ('screen', ptr)]
    x.XGetWindowAttributes.argtypes = [ptr, win, c.POINTER(Attributes)]
    error_type = c.CFUNCTYPE(integer, ptr, ptr)
    error_handler = error_type(lambda _display, _event: 0)
    x.XSetErrorHandler.argtypes = [ptr]; x.XSetErrorHandler.restype = ptr
    previous = x.XSetErrorHandler(c.cast(error_handler, ptr))
    display = x.XOpenDisplay(display_name.encode())
    if not display:
        x.XSetErrorHandler(previous)
        raise RuntimeError('native_chooser_X11_connection_failed')
    try:
        root = x.XDefaultRootWindow(display)
        clients_atom = x.XInternAtom(display, b'_NET_CLIENT_LIST', False)
        class_atom = x.XInternAtom(display, b'WM_CLASS', False)
        def property_value(window, key):
            actual, fmt, count, after, data = atom(), integer(), ulong(), ulong(), ptr()
            status = x.XGetWindowProperty(display, window, key, 0, 4096, False, 0,
                c.byref(actual), c.byref(fmt), c.byref(count), c.byref(after), c.byref(data))
            try:
                if status or after.value or count.value > 4096:
                    raise RuntimeError('native_chooser_X11_property_limit')
                if not data or not actual.value:
                    return None
                if fmt.value == 32:
                    return list(c.cast(data, c.POINTER(ulong))[:count.value])
                if fmt.value == 8:
                    return c.string_at(data, count.value)
                return None
            finally:
                if data: x.XFree(data)
        ids = property_value(root, clients_atom)
        method = '_NET_CLIENT_LIST'
        if not isinstance(ids, list) or not ids:
            # Match the existing recorder's bounded fallback on this actual
            # Hyprland: depth<=2 and at most4096 visited children, never titles.
            method = 'bounded_XQueryTree_depth2_count4096'
            ids, pending, visited = [], [(root, 0)], 0
            while pending:
                parent, depth = pending.pop()
                tree_root, ancestor, children, count = win(), win(), c.POINTER(win)(), c.c_uint()
                if not x.XQueryTree(display, parent, c.byref(tree_root), c.byref(ancestor), c.byref(children), c.byref(count)):
                    continue
                try:
                    if count.value > 4096 or visited + count.value > 4096:
                        raise RuntimeError('native_chooser_window_tree_limit')
                    visited += count.value
                    for i in range(count.value):
                        xid = int(children[i]); ids.append(xid)
                        if depth < 2: pending.append((xid, depth + 1))
                finally:
                    if children: x.XFree(children)
        result = []
        for xid in set(ids):
            try:
                actual_pid = x11_server_pid(xid, display_name)
            except RuntimeError:
                continue
            if actual_pid != pid:
                continue
            wm_class = property_value(xid, class_atom)
            if not isinstance(wm_class, bytes) or not {b'kdialog', b'org.kde.kdialog'}.intersection(wm_class.split(b'\0')):
                continue
            attributes, transient = Attributes(), win()
            if not x.XGetWindowAttributes(display, xid, c.byref(attributes)) or attributes.map_state != 2:
                continue
            hint = bool(x.XGetTransientForHint(display, xid, c.byref(transient)))
            result.append({'xid': xid, 'xres_pid': actual_pid, 'viewable': True,
                           'transient_for': int(transient.value) if hint else None,
                           'method': method})
        return select_parented_window(result, expected_parent)
    finally:
        x.XCloseDisplay(display)
        x.XSetErrorHandler(previous)


def owned_chooser_input_focus(pid, display_name, main_xid):
    """Attest actual X input focus within the fixed chooser's widget family."""
    from workspace.capture import x11_server_pid
    x = c.CDLL(ctypes.util.find_library('X11'))
    ptr, win = c.c_void_p, c.c_ulong
    x.XOpenDisplay.argtypes=[c.c_char_p]; x.XOpenDisplay.restype=ptr
    x.XCloseDisplay.argtypes=[ptr]
    x.XGetInputFocus.argtypes=[ptr,c.POINTER(win),c.POINTER(c.c_int)]
    x.XQueryTree.argtypes=[ptr,win,c.POINTER(win),c.POINTER(win),c.POINTER(c.POINTER(win)),c.POINTER(c.c_uint)]
    x.XGetTransientForHint.argtypes=[ptr,win,c.POINTER(win)]
    x.XFree.argtypes=[ptr]
    handler_type=c.CFUNCTYPE(c.c_int,ptr,ptr)
    handler=handler_type(lambda _d,_e:0)
    x.XSetErrorHandler.argtypes=[ptr]; x.XSetErrorHandler.restype=ptr
    previous=x.XSetErrorHandler(c.cast(handler,ptr)); display=x.XOpenDisplay(display_name.encode())
    if not display:
        x.XSetErrorHandler(previous)
        raise RuntimeError('native_chooser_focus_X11_unavailable')
    try:
        focus,revert=win(),c.c_int();x.XGetInputFocus(display,c.byref(focus),c.byref(revert))
        if focus.value<=1 or x11_server_pid(focus.value,display_name)!=pid:
            raise RuntimeError('native_chooser_focus_XRes_owner_changed')
        pending,seen=[(focus.value,0)],set()
        while pending:
            node,depth=pending.pop()
            if node in seen:continue
            seen.add(node)
            if len(seen)>16:raise RuntimeError('native_chooser_focus_ancestry_limit')
            if node==main_xid:
                return {'within_owned_chooser':True,'input_focus_xid':int(focus.value),'XRes_PID':pid,
                        'verified_main_xid':main_xid,'ancestry_nodes_observed':len(seen)}
            if depth>=8:continue
            root,parent,children,count=win(),win(),c.POINTER(win)(),c.c_uint()
            try:
                if x.XQueryTree(display,node,c.byref(root),c.byref(parent),c.byref(children),c.byref(count)) and parent.value>1:
                    pending.append((parent.value,depth+1))
            finally:
                if children:x.XFree(children)
            transient=win()
            if x.XGetTransientForHint(display,node,c.byref(transient)) and transient.value>1:
                pending.append((transient.value,depth+1))
        raise RuntimeError('native_chooser_focus_outside_attested_widget_family')
    finally:
        x.XCloseDisplay(display);x.XSetErrorHandler(previous)


def chooser_identity(client, process, helper, server, uid, helper_source, parent_xid, x11):
    expected = ['/usr/bin/kdialog', '--title', CAPTION, '--attach', str(parent_xid),
                '--getexistingdirectory', str(Path.home())]
    helper_args = helper.get('argv', [])
    try:
        deadline = float(helper_args[3]) if len(helper_args) == 4 else float('nan')
    except (ValueError, TypeError):
        deadline = float('nan')
    if (client.get('pid') != process.get('pid') or process.get('parent') != helper.get('pid')
            or helper.get('parent') != server.get('pid')
            or process.get('uids') != [uid] * 4 or helper.get('uids') != [uid] * 4
            or process.get('argv') != expected
            or helper_args[:3] != ['/usr/bin/python3', '-I', helper_source] or not math.isfinite(deadline) or deadline <= 0
            or client.get('class') not in ('kdialog', 'org.kde.kdialog')
            or not client.get('title', '').startswith(CAPTION)
            or not re.fullmatch(r'0x[0-9a-f]+', client.get('address', ''))
            or type(x11.get('xid')) is not int or x11['xid'] <= 0
            or x11.get('xres_pid') != process.get('pid') or x11.get('viewable') is not True):
        raise RuntimeError('exact_owned_parented_chooser_required')
    return {'pid': process['pid'], 'start': process['start'], 'address': client['address'],
            'helper_pid': helper['pid'], 'helper_start': helper['start'], 'helper_deadline': helper_args[3],
            'server_pid': server['pid'], 'server_start': server['start'],
            'xid': x11['xid'], 'parent_xid': parent_xid, 'transient_for': x11.get('transient_for'),
            'x11_selection_method': x11['method']}


class NativePickerDriver:
    def __init__(self, server_pid, server_source, command=None, process_reader=process_identity,
                 clock=time.monotonic, sleep=time.sleep, parent_resolver=None, x11_reader=owned_chooser_x11, request_observer=None, focus_reader=owned_chooser_input_focus):
        if parent_resolver is None:
            from workspace.capture import owned_x11_window
            parent_resolver = owned_x11_window
        self.process_reader, self.clock, self.sleep = process_reader, clock, sleep
        self.command, self.x11_reader = command or self._command, x11_reader
        self.focus_reader, self.completion_focus = focus_reader, {}
        self.request_observer = request_observer
        self.uid = os.getuid()
        self.server_source = str(Path(server_source).resolve())
        self.helper_source = str(Path(self.server_source).with_name('native_picker.py'))
        self.server = self.process_reader(server_pid)
        if self.uid == 0 or self.server['uids'] != [self.uid] * 4 or self.server['argv'] != ['/usr/bin/python3', '-I', self.server_source]:
            raise RuntimeError('actual_unprivileged_production_server_required')
        self.parent_resolver = parent_resolver
        self.parent_xid, self.display = parent_resolver()
        if type(self.parent_xid) is not int or not 0 < self.parent_xid <= 0xFFFFFFFF or not re.fullmatch(r':\d+(?:\.\d+)?', self.display):
            raise RuntimeError('verified_Hermes_X11_parent_required')
        self.seen, self.target = set(), None
        if self._candidates():
            raise RuntimeError('preserve_preexisting_native_chooser')

    def _command(self, args):
        remaining = getattr(self, 'deadline', self.clock() + 3) - self.clock()
        if remaining <= 0:
            raise TimeoutError('bounded_native_picker_deadline')
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=min(3, remaining), check=True)
        if len(result.stdout) > 256 * 1024:
            raise RuntimeError('bounded_native_metadata_required')
        return result.stdout

    def _clients(self):
        return json.loads(self.command(['/usr/bin/hyprctl', 'clients', '-j']))

    def _candidates(self):
        if self.process_reader(self.server['pid']) != self.server:
            raise RuntimeError('production_server_identity_changed')
        if self.parent_resolver() != (self.parent_xid, self.display):
            raise RuntimeError('Hermes_X11_parent_identity_changed')
        choices = []
        for client in self._clients():
            # Completion popups are separate compositor clients of the same process.
            # Caption only narrows candidates; XRes, parent and argv still attest identity.
            if (client.get('class') not in ('kdialog', 'org.kde.kdialog')
                    or not client.get('title', '').startswith(CAPTION)):
                continue
            try:
                process = self.process_reader(client['pid'])
                helper = self.process_reader(process['parent'])
            except (OSError, ValueError, KeyError):
                continue
            if helper.get('parent') != self.server['pid']:
                continue
            x11 = self.x11_reader(process['pid'], self.display, self.parent_xid)
            choices.append(chooser_identity(client, process, helper, self.server, self.uid,
                                             self.helper_source, self.parent_xid, x11))
        return choices

    def _current(self):
        choices = self._candidates()
        if len(choices) != 1 or choices[0] != self.target:
            raise RuntimeError('native_chooser_target_changed')
        clients = [row for row in self._clients() if row.get('address') == self.target['address']]
        if len(clients) != 1 or clients[0].get('pid') != self.target['pid']:
            raise RuntimeError('native_chooser_target_changed')
        return clients[0]

    def _already_parented_and_ready(self):
        client = self._current()
        if self.target['transient_for'] != self.parent_xid:
            raise RuntimeError('native_chooser_transient_parent_incorrect')
        if client.get('xwayland') is not True or client.get('floating') is not True:
            raise RuntimeError('native_chooser_not_already_XWayland_and_floating')
        if client.get('mapped') is not True or client.get('hidden') is not False:
            raise RuntimeError('native_chooser_not_already_visible')
        active = json.loads(self.command(['/usr/bin/hyprctl', 'activewindow', '-j']))
        if active.get('pid') != self.target['pid']:
            raise RuntimeError('native_chooser_focus_changed')
        if active.get('address') != self.target['address']:
            if active.get('class') not in ('kdialog','org.kde.kdialog'):
                raise RuntimeError('native_chooser_focus_changed')
            proof = self.focus_reader(self.target['pid'],self.display,self.target['xid'])
            if proof.get('within_owned_chooser') is not True:
                raise RuntimeError('native_chooser_focus_outside_attested_widget_family')
            self.completion_focus[proof['input_focus_xid']] = proof
            if len(self.completion_focus)>16:
                raise RuntimeError('native_chooser_focus_ancestry_limit')

    def _key(self, mods, key, allow_exit=False):
        if self.clock() > self.deadline:
            raise TimeoutError('bounded_native_picker_deadline')
        self._already_parented_and_ready()
        if self.clock() > self.deadline:
            raise TimeoutError('bounded_native_picker_deadline')
        code = 'hl.dsp.send_shortcut({mods=' + json.dumps(mods) + ',key=' + json.dumps(key) + ',window=' + json.dumps('address:' + self.target['address']) + '})'
        if self.command(['/usr/bin/hyprctl', 'dispatch', code]).strip() != 'ok':
            raise RuntimeError('targeted_native_shortcut_not_acknowledged')
        self.keys += 1
        self.last_key = {'mods': mods, 'key': key}
        self.sleep(.025)
        if allow_exit and not self._candidates():
            return False
        self._current()
        return True

    def _cleanup(self):
        # No focus or typing during cleanup. A changed identity is left alone.
        until = self.clock() + 3
        self.deadline = until
        try:
            self._current()
            if self.clock() > until:
                return {'status': 'deadline_expired_before_close'}
            code = 'hl.dsp.window.close({window=' + json.dumps('address:' + self.target['address']) + '})'
            if self.command(['/usr/bin/hyprctl', 'dispatch', code]).strip() != 'ok':
                raise RuntimeError('owned_native_close_not_acknowledged')
            return {'status': 'exact_owned_close_acknowledged'}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, TimeoutError) as error:
            return {'status': 'refused_or_failed', 'error_kind': type(error).__name__}

    def __call__(self, phase, source):
        if phase not in ('cancel_picker', 'preview_cancel', 'commit'):
            raise ValueError('fixed_picker_phase_required')
        keys = path_keys(source)
        self.deadline, self.keys = self.clock() + 25, 0
        self.last_key = None
        while self.clock() < self.deadline:
            choices = self._candidates()
            if len(choices) > 1:
                raise RuntimeError('unique_owned_native_chooser_required')
            if choices:
                self.target = choices[0]
                if (self.target['pid'], self.target['start']) in self.seen:
                    raise RuntimeError('fresh_native_chooser_required')
                break
            if self.request_observer is not None:
                outcome = self.request_observer(phase)
                if outcome is not None:
                    self.last_failure = {'stage': 'request_completed_before_chooser', 'request_outcome': outcome,
                                         'targeted_shortcuts': 0, 'float_applied': False, 'focus_applied': False}
                    raise RuntimeError('native_picker_request_completed_before_observed_chooser')
            self.sleep(.1)
        else:
            raise TimeoutError('actual_native_chooser_not_observed')
        self.seen.add((self.target['pid'], self.target['start']))
        try:
            self._already_parented_and_ready()
            if phase == 'cancel_picker':
                self._key('', 'Escape', allow_exit=True)
            else:
                self._key('CTRL', 'l')
                self._key('CTRL', 'a')
                for mods, key in keys:
                    self._key(mods, key)
                still_open = self._key('', 'Return', allow_exit=True)
                if still_open:
                    self.sleep(.25)
                    self._key('', 'Return', allow_exit=True)
            while self.clock() < self.deadline and self._candidates():
                self.sleep(.1)
            if self._candidates():
                raise TimeoutError('native_chooser_did_not_finish')
            return {'actual_native_chooser': True, 'phase': phase, 'target': self.target,
                    'unassisted_parenting': {'verified_transient_parent': True, 'already_XWayland': True,
                        'already_floating': True, 'already_active': True, 'float_applied': False,
                        'focus_applied': False, 'global_rules_changed': False},
                    'targeted_shortcuts': self.keys,
                    'owned_completion_focus': list(self.completion_focus.values()),
                    'input_scope': 'Targeted native compositor key events; not physical user input.',
                    'result_scope': 'Chooser closed without operator window adaptation; caller must separately verify actual preview/cancel, copied bytes and preserved source.'}
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, TimeoutError) as error:
            self.last_failure = {'error_kind': type(error).__name__, 'target': dict(self.target),
                                 'cleanup': self._cleanup(), 'targeted_shortcuts': self.keys,
                                 'float_applied': False, 'focus_applied': False,
                                 'last_acknowledged_key': self.last_key}
            if isinstance(error, ChooserWindowObservationError):
                self.last_failure['x11_observation'] = error.observation
            raise
