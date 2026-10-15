"""Only public display-session coordinates cross into native GUI launches."""
import os
import subprocess

DISPLAY_KEYS = {'WAYLAND_DISPLAY', 'DISPLAY', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
                'QT_QPA_PLATFORM', 'HYPRLAND_INSTANCE_SIGNATURE'}


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
