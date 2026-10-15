"""Unprivileged lifecycle bridge for the unchanged desktop pin/user service.

The system manager creates the private mount namespace before dropping to the
operator UID. The UI stays unprivileged and socket-activated. This client grants
no system-manager privileges: restart stops only its own verified UI process.
"""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import urllib.request

UNIT = 'hermes-workspace-runtime.service'
SOURCE = Path(__file__).resolve().with_name('server.py')


def main():
    if os.geteuid() != 1000 or sys.argv[1:] not in (['start'], ['stop']):
        raise SystemExit('fixed_unprivileged_UI_client_required')
    if sys.argv[1] == 'start':
        end = time.monotonic()+15
        while time.monotonic() < end:
            try:
                with urllib.request.urlopen('http://127.0.0.1:18791/health', timeout=1) as response:
                    if json.load(response).get('application') != 'hermes-workspace':
                        raise RuntimeError('production_port_collision')
                return
            except OSError:
                time.sleep(.2)
        raise RuntimeError('production_UI_socket_activation_unavailable')
    value = subprocess.check_output(['/usr/bin/systemctl', 'show', UNIT, '-p', 'MainPID', '--value'], text=True, timeout=5).strip()
    pid = int(value)
    if not pid:
        return
    descriptor = os.pidfd_open(pid)
    try:
        proc = Path('/proc')/str(pid)
        args = (proc/'cmdline').read_bytes().split(b'\0')
        if proc.stat().st_uid != os.getuid() or args[1:3] != [b'-I', os.fsencode(SOURCE)]:
            raise RuntimeError('preserve_unexpected_production_process')
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        if not select.select([descriptor], [], [], 8)[0]:
            raise RuntimeError('production_UI_stop_not_acknowledged')
    except ProcessLookupError:
        pass
    finally:
        os.close(descriptor)


if __name__ == '__main__':
    main()
