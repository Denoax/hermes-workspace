"""No-agent guest helper: fixed health and owned-canary probes, bounded stdin."""
import json
import os
from pathlib import Path
import resource
import socket
import struct
import sys
import time


def connect_test(address, port, family):
    started = time.monotonic()
    with socket.socket(family, socket.SOCK_STREAM) as channel:
        channel.settimeout(1)
        try:
            channel.connect((address, port))
            return {'connected': True, 'wall_seconds': time.monotonic()-started}
        except OSError as error:
            return {'connected': False, 'error': type(error).__name__, 'wall_seconds': time.monotonic()-started}


def main():
    if os.geteuid() == 0:
        raise RuntimeError('guest_probe_user_must_be_nonroot')
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError('probe_input_limit')
    data = json.loads(raw)
    if type(data) is dict and set(data)=={'operation','request'} and data['operation']=='lifecycle_probe' and data['request']=={}:
        import subprocess
        if json.loads(Path('/etc/mani-vmlab/guest.json').read_text()).get('role')!='worker_b':raise ValueError('validation_worker_only')
        result=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-I','/opt/mani-vmlab/lifecycle_probe.py'],capture_output=True,timeout=90)
        if result.returncode:raise RuntimeError('disposable_lifecycle_probe_failed')
        if len(result.stdout)>65536:raise ValueError('lifecycle_reply_limit')
        sys.stdout.buffer.write(result.stdout);return
    if type(data) is dict and set(data)=={'operation','request'} and data['operation'] in ('workspace','validate'):
        import subprocess
        marker=json.loads(Path('/etc/mani-vmlab/guest.json').read_text())
        role=marker.get('role')
        if (data['operation']=='workspace' and role!='worker_a') or (data['operation']=='validate' and role!='worker_b'):
            raise ValueError('fixed_worker_role_required')
        command=['/usr/bin/python3','-I','/opt/mani-vmlab/workspace_job.py'] if data['operation']=='workspace' else ['/usr/bin/sudo','-n','/usr/bin/python3','-I','/opt/mani-vmlab/run_code.py']
        result=subprocess.run(command,input=json.dumps(data['request']).encode(),capture_output=True,timeout=400 if data['operation']=='workspace' else 30)
        if result.returncode:raise RuntimeError('bounded_guest_workspace_operation_failed')
        if len(result.stdout)>131072:raise ValueError('workspace_reply_limit')
        sys.stdout.buffer.write(result.stdout);return
    if type(data) is dict and set(data) == {'operation', 'request'} and data['operation'] == 'solve':
        import subprocess
        request = json.dumps(data['request']).encode()
        if len(request)>32768:
            raise ValueError('solver_request_limit')
        result = subprocess.run(['/usr/bin/python3', '-I', '/opt/mani-vmlab/solve.py'],
                                input=request, capture_output=True, timeout=150)
        if result.returncode:
            sys.stderr.buffer.write(result.stderr[-8192:])
            raise RuntimeError('guest_Hermes_solver_failed')
        if len(result.stdout)>65536:
            raise ValueError('guest_solver_output_limit')
        sys.stdout.buffer.write(result.stdout)
        return
    if type(data) is not dict or set(data) != {'operation'} or data['operation'] not in ('health', 'probe', 'hermes_health'):
        raise ValueError('fixed_probe_schema_only')
    marker = json.loads(Path('/etc/mani-vmlab/guest.json').read_text())
    if marker['agents_enabled'] is not False:
        raise RuntimeError('no_agent_qualification_only')
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    if data['operation'] == 'health':
        ready = not marker.get('runtime_zip_sha256') or Path('/etc/mani-vmlab/installed.json').is_file()
        print(json.dumps({'healthy': ready, 'role': marker['role'], 'agents_enabled': False}))
        return
    if data['operation'] == 'hermes_health':
        # Installation is root-owned, but all runtime imports occur as guest lab.
        import contextlib
        import tempfile
        import inspect
        with tempfile.TemporaryDirectory(prefix='mani-import-') as home, tempfile.TemporaryFile(mode='w+') as logs:
            os.environ['HERMES_HOME'] = home
            sys.path[:0] = ['/opt/hermes', '/opt/hermes-deps']
            with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
                from run_agent import AIAgent
            installed = json.loads(Path('/etc/mani-vmlab/installed.json').read_text())
            print(json.dumps({'uid': os.geteuid(), 'installed': installed,
                'constructor_parameters': sorted(inspect.signature(AIAgent).parameters),
                'agent_conversation_executed': False, 'personal_home_imported': False}))
        return
    # These are owned canaries in this VM's separate host-side network namespace.
    # They are not public destinations, physical LAN endpoints or arbitrary input.
    probes = {}
    for label, address, family in [('host_v4', '10.0.2.2', socket.AF_INET),
                                    ('host_v6', 'fec0::2', socket.AF_INET6),
                                    ('owned_outside_v4', '198.18.0.1', socket.AF_INET),
                                    ('owned_outside_v6', 'fd42:4d41:4e49::1', socket.AF_INET6)]:
        probes[label] = connect_test(address, 18090, family)
    # An explicit UDP DNS-shaped query to the owned namespace canary, with no
    # system resolver and no query to a router/public DNS service.
    query = struct.pack('!6H', 0x4d41, 0x0100, 1, 0, 0, 0) + b'\x06canary\x04test\x00' + struct.pack('!2H', 1, 1)
    for label, address, family in [('DNS_v4', '198.18.0.1', socket.AF_INET), ('DNS_v6', 'fd42:4d41:4e49::1', socket.AF_INET6)]:
        with socket.socket(family, socket.SOCK_DGRAM) as channel:
            channel.settimeout(1)
            try:
                channel.sendto(query, (address, 53))
                channel.recv(2048)
                probes[label] = {'reply_received': True}
            except OSError as error:
                probes[label] = {'reply_received': False, 'error': type(error).__name__}
    print(json.dumps({'probes': probes, 'guest_self_report_is_not_independent_proof': True}))


if __name__ == '__main__':
    main()
