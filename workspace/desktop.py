"""Only public display-session coordinates cross into native GUI launches."""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

DISPLAY_KEYS = {'WAYLAND_DISPLAY', 'DISPLAY', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
                'QT_QPA_PLATFORM', 'HYPRLAND_INSTANCE_SIGNATURE'}

_picker_lock = threading.Lock()
_PICKER_ERRORS = {
    'operator_required': 'Folder selection requires the normal Hermes desktop user.',
    'parent_unavailable': 'The verified Hermes app window is unavailable. Reopen Hermes before choosing a folder.',
    'deadline_exceeded': 'Folder selection timed out. Nothing was imported.',
    'dialog_failed': 'The native folder chooser failed. Nothing was imported.',
    'invalid_selection': 'The native folder chooser returned an invalid selection. Nothing was imported.',
}


def desktop_environment():
    environment = os.environ.copy()
    environment.update(XDG_RUNTIME_DIR='/run/user/1000', DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
    result = subprocess.run(['/usr/bin/systemctl', '--user', 'show-environment'], env=environment,
                            capture_output=True, text=True, timeout=3, check=True)
    # Never log or persist the manager environment. Authentication variables
    # cannot enter this whitelist; GUI session coordinates are refreshed on use.
    for line in result.stdout.splitlines():
        key, separator, value = line.partition('=')
        if separator and key in DISPLAY_KEYS and len(value) <= 512 and '\x00' not in value:
            environment[key] = value
    if not environment.get('WAYLAND_DISPLAY') and not environment.get('DISPLAY'):
        raise RuntimeError('native_desktop_session_unavailable')
    return environment


def _picker_reply(raw):
    try:
        size = len(raw.encode())
    except (AttributeError, UnicodeError):
        raise RuntimeError('native_picker_invalid_reply') from None
    if size > 16384:
        raise RuntimeError('native_picker_invalid_reply')
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError('native_picker_invalid_reply') from None
    if not isinstance(result, dict):
        raise RuntimeError('native_picker_invalid_reply')
    status = result.get('status')
    if status == 'cancelled' and set(result) == {'status'}:
        return result
    if status == 'selected' and set(result) == {'status', 'path'}:
        path = result['path']
        try:
            if isinstance(path, str) and path.startswith('/') and '\0' not in path and len(path.encode()) <= 4096:
                return result
        except UnicodeError:
            pass
    if status == 'error' and set(result) == {'status', 'code'} and isinstance(result['code'], str) and result['code'] in _PICKER_ERRORS:
        raise RuntimeError(_PICKER_ERRORS[result['code']])
    raise RuntimeError('native_picker_invalid_reply')


def choose_import_directory():
    """Keep the complete operation within the existing120s picker budget.

    Only this fixed child performs Xlib/Qt work. Its process group lets timeout
    cleanup reap a blocked helper and its chooser without touching other apps.
    No ambient desktop, selected path, stderr or authentication data is logged.
    """
    deadline = time.monotonic() + 120
    if not _picker_lock.acquire(blocking=False):
        raise RuntimeError('A Hermes folder chooser is already open.')
    try:
        environment = desktop_environment()
        if deadline - time.monotonic() <= 1:
            raise RuntimeError(_PICKER_ERRORS['deadline_exceeded'])
        helper = Path(__file__).with_name('native_picker.py')
        try:
            process = subprocess.Popen(
                ['/usr/bin/python3', '-I', str(helper), repr(deadline - 1)],
                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, start_new_session=True,
            )
        except OSError:
            raise RuntimeError(_PICKER_ERRORS['dialog_failed']) from None
        try:
            raw, _ = process.communicate(timeout=max(0.001, deadline - time.monotonic() - 0.5))
        except subprocess.TimeoutExpired:
            # communicate has not reaped the process, so its PID/session cannot
            # be reused before this owned process-group cleanup.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise RuntimeError('The owned folder chooser did not terminate before its deadline.') from None
            raise RuntimeError(_PICKER_ERRORS['deadline_exceeded']) from None
        if process.returncode != 0:
            raise RuntimeError(_PICKER_ERRORS['dialog_failed'])
        return _picker_reply(raw)
    finally:
        _picker_lock.release()
