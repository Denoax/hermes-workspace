"""Timestamp-preserving browser evidence; no interpolation or invented frames."""
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time


def frame_timeline(frames):
    """Quantize to 1ms while rejecting reversed or excessively colliding clocks."""
    if not frames:
        raise ValueError('recording_has_no_frames')
    origin = float(frames[0][1])
    previous_stamp, previous_pts = origin, -1
    timeline = []
    for path, value in frames:
        stamp = float(value)
        if not math.isfinite(stamp) or not math.isfinite(origin) or stamp < previous_stamp:
            raise ValueError('recording_timestamp_not_finite_or_monotonic')
        delta = (stamp - origin) * 1000
        pts = max(previous_pts + 1, round(delta))
        if abs(pts - delta) > 2.001:
            raise ValueError('recording_timestamp_collision_exceeds_2ms')
        timeline.append((Path(path), pts))
        previous_stamp, previous_pts = stamp, pts
    return timeline


def encode_frames(frames, output, directory):
    try:
        timeline = frame_timeline(frames)
    except ValueError:
        # Keep clock-only adverse evidence before the private JPEGs are cleaned.
        # No interface text, file contents or authentication data is included.
        origin = float(frames[0][1]) if frames else 0
        offsets = [float(stamp) - origin for _, stamp in frames]
        diagnostic = {'kind': 'raw CDP capture timestamp arrival order; not presentation timings',
                      'frames': len(frames),
                      'offset_seconds': [value if math.isfinite(value) else None for value in offsets]}
        Path(str(output) + '.timestamps.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
        raise
    rows = []
    for index, (path, pts) in enumerate(timeline):
        quoted = str(path).replace("'", "'\\''")
        rows += ["file '" + quoted + "'", 'option framerate 1000']
        if index + 1 < len(timeline):
            rows.append('duration ' + format((timeline[index + 1][1] - pts) / 1000, '.3f'))
    concat = Path(directory) / 'frames.txt'
    concat.write_text('\n'.join(rows) + '\n')
    # The image demuxer's default25Hz clock previously coalesced distinct CDP
    # frames. Both the input and encoder now use a millisecond timebase.
    subprocess.run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
                    '-i', str(concat), '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-fps_mode', 'vfr',
                    '-c:v', 'libx264', '-enc_time_base', '1/1000', '-crf', '20', '-pix_fmt', 'yuv420p',
                    str(output)], check=True, timeout=60)
    info = json.loads(subprocess.check_output(['/usr/bin/ffprobe', '-v', 'error', '-select_streams', 'v:0',
                     '-count_frames', '-show_entries', 'stream=nb_read_frames,duration,width,height',
                     '-of', 'json', str(output)], text=True, timeout=60))['streams'][0]
    count = int(info['nb_read_frames'])
    expected_seconds = (timeline[-1][1] + 1) / 1000
    duration = float(info['duration'])
    if count != len(timeline) or abs(duration - expected_seconds) > .005:
        raise RuntimeError('encoded_recording_frame_count_or_timing_mismatch')
    origin = frames[0][1]
    return {'frames': len(frames), 'seconds': frames[-1][1] - origin,
            'encoded_frames': count, 'encoded_seconds': duration, 'dimensions': [info['width'], info['height']],
            'clock': 'Original CDP timestamps quantized to1ms; no interpolation,cuts or speed changes.',
            'maximum_timestamp_quantization_ms': max(abs(pts - (stamp - origin) * 1000) for (_, pts), (_, stamp) in zip(timeline, frames)),
            'audio': 'Silent recording; accepted sample identity/cue checks are separate.',
            'GPU_timings': 'Unmeasured; capture timestamps are not display presentation timings.'}


class Recording:
    def __init__(self, browser, output):
        self.browser = browser
        self.output = Path(output)
        self.temporary = tempfile.TemporaryDirectory(prefix='hermes-motion-')
        self.frames = []
        self.previous = browser.pipe.on_event

        def event(message):
            if message.get('method') == 'Page.screencastFrame':
                params = message['params']
                path = Path(self.temporary.name) / f'{len(self.frames):06d}.jpg'
                path.write_bytes(base64.b64decode(params['data']))
                self.frames.append((path, params['metadata']['timestamp']))
                browser.pipe.counter += 1
                raw = json.dumps({'id': browser.pipe.counter, 'method': 'Page.screencastFrameAck',
                    'params': {'sessionId': params['sessionId']}, 'sessionId': browser.session}).encode() + b'\0'
                while raw:
                    raw = raw[os.write(browser.pipe.write, raw):]
            elif self.previous:
                self.previous(message)

        browser.pipe.on_event = event
        browser.call('Page.startScreencast', {'format': 'jpeg', 'quality': 91, 'maxWidth': 1440,
                                           'maxHeight': 900, 'everyNthFrame': 1})

    def hold(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.browser.evaluate('document.visibilityState')
            time.sleep(.02)

    def finish(self):
        try:
            try:
                self.browser.call('Page.stopScreencast')
            finally:
                self.browser.pipe.on_event = self.previous
            return encode_frames(self.frames, self.output, self.temporary.name)
        finally:
            self.temporary.cleanup()


def x11_server_pid(xid, display_name):
    """Ask XRes for the kernel-side client PID, not a mutable namespaced property.

    Flatpak's _NET_WM_PID may identify the process inside its PID namespace.
    XRes local-client PID binds the resource to its actual server connection.
    """
    import ctypes as c
    import ctypes.util
    names = [ctypes.util.find_library(name) for name in ('xcb', 'xcb-res', 'c')]
    if not all(names):
        raise RuntimeError('native_recording_XRes_unavailable')
    xcb, res, libc = [c.CDLL(name) for name in names]
    class Spec(c.Structure):
        _fields_ = [('client', c.c_uint32), ('mask', c.c_uint32)]
    class Cookie(c.Structure):
        _fields_ = [('sequence', c.c_uint)]
    class Value(c.Structure):
        _fields_ = [('spec', Spec), ('length', c.c_uint32)]
    class Iterator(c.Structure):
        _fields_ = [('data', c.POINTER(Value)), ('rem', c.c_int), ('index', c.c_int)]
    xcb.xcb_connect.argtypes = [c.c_char_p, c.POINTER(c.c_int)]
    xcb.xcb_connect.restype = c.c_void_p
    xcb.xcb_connection_has_error.argtypes = [c.c_void_p]
    xcb.xcb_disconnect.argtypes = [c.c_void_p]
    res.xcb_res_query_client_ids.argtypes = [c.c_void_p, c.c_uint32, c.POINTER(Spec)]
    res.xcb_res_query_client_ids.restype = Cookie
    res.xcb_res_query_client_ids_reply.argtypes = [c.c_void_p, Cookie, c.POINTER(c.c_void_p)]
    res.xcb_res_query_client_ids_reply.restype = c.c_void_p
    res.xcb_res_query_client_ids_ids_iterator.argtypes = [c.c_void_p]
    res.xcb_res_query_client_ids_ids_iterator.restype = Iterator
    res.xcb_res_client_id_value_value.argtypes = [c.POINTER(Value)]
    res.xcb_res_client_id_value_value.restype = c.POINTER(c.c_uint32)
    res.xcb_res_client_id_value_value_length.argtypes = [c.POINTER(Value)]
    res.xcb_res_client_id_value_next.argtypes = [c.POINTER(Iterator)]
    libc.free.argtypes = [c.c_void_p]
    connection = xcb.xcb_connect(display_name.encode(), None)
    reply, error = None, c.c_void_p()
    try:
        if not connection or xcb.xcb_connection_has_error(connection):
            raise RuntimeError('native_recording_XRes_connection_failed')
        spec = Spec(xid, 2)  # XCB_RES_CLIENT_ID_MASK_LOCAL_CLIENT_PID
        cookie = res.xcb_res_query_client_ids(connection, 1, c.byref(spec))
        reply = res.xcb_res_query_client_ids_reply(connection, cookie, c.byref(error))
        if error.value or not reply:
            raise RuntimeError('native_recording_XRes_query_failed')
        iterator = res.xcb_res_query_client_ids_ids_iterator(reply)
        if not 0 <= iterator.rem <= 8:
            raise RuntimeError('native_recording_XRes_reply_limit')
        pids = []
        while iterator.rem:
            value = iterator.data.contents
            if value.spec.mask == 2 and res.xcb_res_client_id_value_value_length(iterator.data) == 1:
                pids.append(int(res.xcb_res_client_id_value_value(iterator.data)[0]))
            res.xcb_res_client_id_value_next(c.byref(iterator))
        if len(set(pids)) != 1 or pids[0] <= 0:
            raise RuntimeError('native_recording_XRes_PID_not_unique')
        return pids[0]
    finally:
        if reply: libc.free(reply)
        if error.value: libc.free(error)
        if connection: xcb.xcb_disconnect(connection)


def owned_x11_window(diagnostics=None):
    """Resolve only the dedicated profile's app window via installed Xlib.

    Hyprland need not publish EWMH's client list, and xwininfo is not installed.
    This readonly adapter checks the same process/profile and exact WM_CLASS
    before returning an XID. XRes supplies the server-side PID; mutable _NET_WM_PID is not trusted. It never selects the root/whole-desktop window.
    """
    import ctypes
    import ctypes.util
    import re
    from workspace.launcher import owns_browser
    display_name = os.environ.get('DISPLAY', '')
    if not re.fullmatch(r':\d+(?:\.\d+)?', display_name):
        raise RuntimeError('native_recording_requires_local_X_display')
    library = ctypes.util.find_library('X11')
    if not library:
        raise RuntimeError('native_recording_Xlib_unavailable')
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update({'candidate_windows': [], 'selection': 'unique viewable bounds-matching XRes/profile-owned Hermes window'})
    native_clients = json.loads(subprocess.check_output(['/usr/bin/hyprctl', 'clients', '-j'], text=True, timeout=4))
    surfaces = [row for row in native_clients if row.get('class') == 'HermesWorkspace' and owns_browser(row.get('pid'))]
    if len(surfaces) != 1:
        raise RuntimeError('native_recording_owned_surface_not_unique')
    surface = surfaces[0]
    from workspace.native_coordinates import read_layout, translate_rectangle
    layout = read_layout()
    expected_position, expected_size = translate_rectangle(layout, surface['at'], surface['size'])
    diagnostics['expected_bounds'] = {'position': surface['at'], 'size': surface['size']}
    diagnostics['expected_X11_bounds'] = {'position': expected_position, 'size': expected_size}
    diagnostics['coordinate_mapping'] = 'Exact output-name match, equal coordinate units; no output reconfiguration.'
    x = ctypes.CDLL(library)
    pointer, window, atom, integer, ulong = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]; x.XOpenDisplay.restype = pointer
    x.XCloseDisplay.argtypes = [pointer]
    x.XDefaultRootWindow.argtypes = [pointer]; x.XDefaultRootWindow.restype = window
    x.XInternAtom.argtypes = [pointer, ctypes.c_char_p, integer]; x.XInternAtom.restype = atom
    x.XQueryTree.argtypes = [pointer, window, ctypes.POINTER(window), ctypes.POINTER(window), ctypes.POINTER(ctypes.POINTER(window)), ctypes.POINTER(ctypes.c_uint)]
    x.XGetWindowProperty.argtypes = [pointer, window, atom, ctypes.c_long, ctypes.c_long, integer, atom,
        ctypes.POINTER(atom), ctypes.POINTER(integer), ctypes.POINTER(ulong), ctypes.POINTER(ulong), ctypes.POINTER(pointer)]
    x.XFree.argtypes = [pointer]
    class Attributes(ctypes.Structure):
        _fields_ = [('x', integer), ('y', integer), ('width', integer), ('height', integer),
            ('border_width', integer), ('depth', integer), ('visual', pointer), ('root', window),
            ('class_', integer), ('bit_gravity', integer), ('win_gravity', integer), ('backing_store', integer),
            ('backing_planes', ulong), ('backing_pixel', ulong), ('save_under', integer), ('colormap', window),
            ('map_installed', integer), ('map_state', integer), ('all_event_masks', ctypes.c_long),
            ('your_event_mask', ctypes.c_long), ('do_not_propagate_mask', ctypes.c_long),
            ('override_redirect', integer), ('screen', pointer)]
    x.XGetWindowAttributes.argtypes = [pointer, window, ctypes.POINTER(Attributes)]
    x.XTranslateCoordinates.argtypes = [pointer, window, window, integer, integer,
        ctypes.POINTER(integer), ctypes.POINTER(integer), ctypes.POINTER(window)]
    # A disappearing window during a readonly tree walk is an ordinary race.
    handler_type = ctypes.CFUNCTYPE(integer, pointer, pointer)
    handler = handler_type(lambda _display, _event: 0)
    x.XSetErrorHandler.argtypes = [pointer]
    x.XSetErrorHandler.restype = pointer
    previous_handler = x.XSetErrorHandler(ctypes.cast(handler, pointer))
    display = x.XOpenDisplay(display_name.encode())
    if not display:
        x.XSetErrorHandler(previous_handler)
        raise RuntimeError('native_recording_X_display_unavailable')
    try:
        class_atom = x.XInternAtom(display, b'WM_CLASS', 1)
        if not class_atom:
            raise RuntimeError('native_recording_app_atoms_missing')
        def property_value(xid, property_atom):
            actual, fmt, count, remaining, data = atom(), integer(), ulong(), ulong(), pointer()
            status = x.XGetWindowProperty(display, xid, property_atom, 0, 1024, 0, 0,
                ctypes.byref(actual), ctypes.byref(fmt), ctypes.byref(count), ctypes.byref(remaining), ctypes.byref(data))
            try:
                if status or not data.value or remaining.value:
                    return None
                if fmt.value == 32 and count.value == 1:
                    return ctypes.cast(data, ctypes.POINTER(ulong))[0]
                if fmt.value == 8 and count.value <= 4096:
                    return ctypes.string_at(data, count.value)
            finally:
                if data.value: x.XFree(data)
            return None
        pending = [(x.XDefaultRootWindow(display), 0)]
        visited, matches = 0, []
        while pending:
            parent, depth = pending.pop()
            root, ancestor, children, count = window(), window(), ctypes.POINTER(window)(), ctypes.c_uint()
            if not x.XQueryTree(display, parent, ctypes.byref(root), ctypes.byref(ancestor), ctypes.byref(children), ctypes.byref(count)):
                continue
            try:
                if count.value > 4096 or visited + count.value > 4096:
                    raise RuntimeError('native_recording_window_tree_limit')
                for index in range(count.value):
                    xid = int(children[index]); visited += 1
                    names = property_value(xid, class_atom)
                    if isinstance(names, bytes):
                        try:
                            pid = x11_server_pid(xid, display_name)
                        except RuntimeError:
                            pid = None
                        owned = bool(pid and owns_browser(pid))
                        named = b'HermesWorkspace' in names.split(b'\0')
                        if owned or named:
                            attributes = Attributes()
                            px, py, child = integer(), integer(), window()
                            got_attributes = bool(x.XGetWindowAttributes(display, xid, ctypes.byref(attributes)))
                            translated = bool(x.XTranslateCoordinates(display, xid, x.XDefaultRootWindow(display), 0, 0,
                                ctypes.byref(px), ctypes.byref(py), ctypes.byref(child)))
                            size = [attributes.width, attributes.height]
                            position = [px.value, py.value]
                            bounds_match = got_attributes and translated and tuple(size) == expected_size and all(abs(a-b) <= 1 for a,b in zip(position, expected_position))
                            row = {'XID': xid, 'WM_CLASS': names.decode('utf-8', 'replace').split('\0'),
                                   'server_PID': pid, 'profile_owned': owned, 'viewable': got_attributes and attributes.map_state == 2,
                                   'position': position, 'size': size, 'native_bounds_match': bounds_match}
                            diagnostics['candidate_windows'].append(row)
                            if owned and named and row['viewable'] and bounds_match:
                                matches.append(xid)
                    if depth < 2: pending.append((xid, depth + 1))
            finally:
                if children: x.XFree(children)
        diagnostics['matching_visible_owned_windows'] = len(set(matches))
        if len(set(matches)) != 1:
            raise RuntimeError('native_recording_owned_X11_window_not_unique')
        if read_layout() != layout:
            raise RuntimeError('native_output_layout_changed_during_attestation')
        return matches[0], display_name
    finally:
        x.XCloseDisplay(display)
        x.XSetErrorHandler(previous_handler)


class NativeWindowRecording:
    """FFmpeg window-only acquisition, without CDP's asynchronous image clock.

    Official interface: https://ffmpeg.org/ffmpeg-devices.html#x11grab
    No desktop root capture, audio input, interpolation or display change.
    """
    def __init__(self, browser, output):
        self.browser, self.output = browser, Path(output)
        identity = {}
        try:
            xid, display = owned_x11_window(identity)
        finally:
            Path(str(self.output) + '.window.json').write_text(json.dumps(identity, indent=2) + '\n')
        self.process = subprocess.Popen(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-y',
            '-f', 'x11grab', '-framerate', '60', '-draw_mouse', '1', '-window_id', str(xid), '-i', display,
            '-t', '30', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-fps_mode', 'passthrough',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', str(self.output)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(.2)
        if self.process.poll() is not None:
            self.process.communicate(timeout=2)
            raise RuntimeError('native_window_recording_start_failed')

    hold = Recording.hold

    def finish(self):
        import signal
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
        try:
            _out, error = self.process.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.communicate(timeout=5)
            raise RuntimeError('native_window_recording_stop_timeout')
        if self.process.returncode not in (0, 255) or not self.output.is_file():
            raise RuntimeError('native_window_recording_failed')
        info = json.loads(subprocess.check_output(['/usr/bin/ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_frames', '-show_entries', 'stream=nb_read_frames,duration,width,height,avg_frame_rate',
            '-of', 'json', str(self.output)], text=True, timeout=30))['streams'][0]
        count, duration = int(info['nb_read_frames']), float(info['duration'])
        if count < 10 or duration <= 0 or duration > 31:
            raise RuntimeError('native_window_recording_empty_or_unbounded')
        return {'method': 'native XWayland window-only x11grab; XRes server PID/profile and WM_CLASS verified',
                'frames': count, 'encoded_frames': count, 'seconds': duration, 'encoded_seconds': duration,
                'frame_count_scope': 'Decoded frames in the delivered recording; acquisition frame loss is unmeasured.',
                'dimensions': [info['width'], info['height']], 'configured_sample_rate': 60,
                'average_encoded_rate': info['avg_frame_rate'], 'clock': 'Native FFmpeg acquisition timestamps; passthrough, no interpolation, cuts or speed changes.',
                'audio': 'Silent; no microphone or desktop audio captured.',
                'scope': 'Only the verified Hermes app XID, never the desktop root window.',
                'source_documentation': 'https://ffmpeg.org/ffmpeg-devices.html#x11grab',
                'GPU_timings': 'Unmeasured; capture sampling is not presentation or physical-display approval.'}
