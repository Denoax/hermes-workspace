"""Outside inference window: fixed normal service, bounded lease, restoration."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import secrets
import stat
import subprocess
import time
import urllib.request

DIRECTORY = Path('/home/mani-vmlab-data/window')
STATE = DIRECTORY/'state.json'
SERVICE = 'mani-vmlab-inference-window.service'
NORMAL = 'manibot-llama.service'
# Runtime control overrides precede the persistent user service directory.
MASK_DIRECTORY = Path('/run/user/1000/systemd/user.control')
CONFIGS = (Path('/home/mani/.config/systemd/user/manibot-llama.service'),
           Path('/home/mani/.local/bin/start-manibot-llama'),
           Path('/home/mani/.config/systemd/user/qwen-local.service'),
           Path('/home/mani/.hermes/config.yaml'))


def command(args, timeout=30):
    return subprocess.check_output(args, stderr=subprocess.PIPE, timeout=timeout,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'XDG_RUNTIME_DIR': '/run/user/1000',
             'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'})


def normal_command(*args):
    return command(['/usr/bin/setpriv', '--reuid=1000', '--regid=1000', '--init-groups',
                    '/usr/bin/systemctl', '--user', *args, NORMAL], timeout=180)


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {'status': 'closed'}


def mutate(update):
    from lab.state import atomic_json
    with (DIRECTORY/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = state()
        update(record)
        atomic_json(STATE, record)
        return record


def active():
    record = state()
    return (record.get('status') == 'active' and record.get('normal_quiesced') is True
            and record.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and time.monotonic() < record['deadline'] and time.monotonic()-record['heartbeat'] < 45)


def mask_directory():
    descriptor=os.open(MASK_DIRECTORY,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    info=os.fstat(descriptor)
    if info.st_uid!=1000 or info.st_mode & 0o022:
        os.close(descriptor)
        raise RuntimeError('owned_user_runtime_directory_required')
    return descriptor,info


def create_mask():
    descriptor,directory=mask_directory()
    temporary='.mani-vmlab-mask-'+secrets.token_hex(8)
    try:
        os.symlink('/dev/null',temporary,dir_fd=descriptor)
        info=os.stat(temporary,dir_fd=descriptor,follow_symlinks=False)
        # Persist identity before publication, so owner death cannot leave an
        # unrecorded mask. Hard-link creation refuses any existing destination.
        mask={'directory_device':directory.st_dev,'directory_inode':directory.st_ino,
              'device':info.st_dev,'inode':info.st_ino,'temporary':temporary}
        mutate(lambda r:r.update(runtime_mask=mask))
        os.link(temporary,NORMAL,src_dir_fd=descriptor,dst_dir_fd=descriptor,follow_symlinks=False)
        os.unlink(temporary,dir_fd=descriptor)
        command(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
                 '/usr/bin/systemctl','--user','daemon-reload'])
        if normal_command('show','-p','LoadState','--value').strip()!=b'masked':
            raise RuntimeError('runtime_mask_not_effective')
    finally:
        os.close(descriptor)


def owned_mask(remove=False):
    mask=state().get('runtime_mask')
    if not mask:return False
    descriptor,directory=mask_directory()
    try:
        if (directory.st_dev,directory.st_ino)!=(mask['directory_device'],mask['directory_inode']):
            raise RuntimeError('preserve_changed_mask_directory')
        present=False
        for name in (NORMAL,mask['temporary']):
            try:info=os.stat(name,dir_fd=descriptor,follow_symlinks=False)
            except FileNotFoundError:continue
            if (info.st_dev,info.st_ino)!=(mask['device'],mask['inode']) or info.st_uid!=0 or not stat.S_ISLNK(info.st_mode):
                raise RuntimeError('preserve_changed_runtime_mask')
            if os.readlink(name,dir_fd=descriptor)!='/dev/null':raise RuntimeError('preserve_changed_mask_target')
            if name==NORMAL:present=True
            if remove:os.unlink(name,dir_fd=descriptor)
        return present
    finally:
        os.close(descriptor)


def beat():
    if not active():
        raise RuntimeError('bounded_inference_window_not_active')
    mutate(lambda r:r.update(heartbeat=time.monotonic()))


def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        address = '\0'+address[1:] if address.startswith('@') else address
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
            channel.sendto(message.encode(), address)


def guard():
    if state().get('status') in ('opening', 'active', 'restoring'):
        raise RuntimeError('recover_existing_window_first')
    if (MASK_DIRECTORY/NORMAL).exists() or (MASK_DIRECTORY/NORMAL).is_symlink():
        raise RuntimeError('preserve_preexisting_runtime_unit_override')
    was_active = normal_command('is-active').strip() == b'active'
    if not was_active:
        raise RuntimeError('expected_original_normal_service_active')
    with urllib.request.urlopen('http://127.0.0.1:8080/slots', timeout=3) as response:
        slots = json.load(response)
    if any(slot.get('is_processing') is not False for slot in slots):
        raise RuntimeError('normal_inference_in_progress')
    before = {'status': 'opening', 'prior_active': was_active,
        'prior_PID': int(normal_command('show', '-p', 'MainPID', '--value')),
        'configuration_sha256': {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in CONFIGS},
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'deadline': time.monotonic()+1800, 'heartbeat':time.monotonic()}
    mutate(lambda r:(r.clear(), r.update(before)))
    create_mask()
    normal_command('stop')
    if normal_command('show','-p','MainPID','--value').strip()!=b'0':
        raise RuntimeError('normal_service_not_quiesced')
    mutate(lambda r:r.update(status='active',normal_quiesced=True,
        quiescence_proof={'LoadState':'masked','MainPID':0,'mask_directory':str(MASK_DIRECTORY)}))
    notify('READY=1')
    while active():
        if (not owned_mask()
                or normal_command('show','-p','LoadState','--value').strip()!=b'masked'
                or normal_command('show','-p','MainPID','--value').strip()!=b'0'):
            mutate(lambda r:r.update(normal_quiesced=False))
            break
        if command(['/usr/bin/systemctl', 'is-active', 'mani-vmlab-supervisor.service']).strip() != b'active':
            break
        notify('WATCHDOG=1')
        time.sleep(0.25)


def restore():
    record = state()
    if record.get('status') not in ('opening', 'active', 'restoring'):
        return record
    mutate(lambda r:r.update(status='restoring',normal_quiesced=False))
    # BindsTo stops every owned VM/backend before normal GPU use is restored.
    command(['/usr/bin/systemctl', 'stop', 'mani-vmlab-supervisor.service'], timeout=30)
    if record.get('runtime_mask'):
        owned_mask(remove=True)
        command(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups',
                 '/usr/bin/systemctl','--user','daemon-reload'])
    if record.get('prior_active'):
        normal_command('start')
    healthy = False
    for _ in range(180):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=1) as response:
                healthy = json.load(response).get('status') == 'ok'
            if healthy:
                with urllib.request.urlopen('http://127.0.0.1:8080/props',timeout=1) as response:props=json.load(response)
                healthy=props.get('model_alias')=='qwen3.6-35b-a3b-q4' and props.get('default_generation_settings',{}).get('n_ctx')==65536
        except (OSError, ValueError):
            pass
        if healthy:
            break
        time.sleep(1)
    hashes_equal = {p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
                    for p,h in record['configuration_sha256'].items()}
    mask_removed=not (MASK_DIRECTORY/NORMAL).exists() and not (MASK_DIRECTORY/NORMAL).is_symlink()
    result=mutate(lambda r:r.update(status='closed' if healthy and mask_removed and all(hashes_equal.values()) else 'restore_failed',
        runtime_mask_removed=mask_removed,
        restored_health=healthy, configuration_hashes_equal=hashes_equal,
        restored_PID=int(normal_command('show', '-p', 'MainPID', '--value'))))
    from lab.state import atomic_json
    snapshot={'status':result['status'],'ledger':'native_root_owned','broker_version':1,
        'runtime_stage':result['status'],'boot_id':result['boot_id'],'observed_monotonic_seconds':time.monotonic(),
        'observed_facts':{'inference_window_active':False,'owned_fleet_active':False},
        'normal_restoration':{'healthy':healthy,'configuration_hashes_equal':hashes_equal,'mask_removed':mask_removed},
        'remaining_seconds':0}
    public=Path('/var/lib/mani-vmlab-review/status-public.json')
    atomic_json(public,snapshot);public.chmod(0o644)
    configuration=Path('/etc/mani-vmlab/config.json')
    if result['status']=='closed' and configuration.exists() and json.loads(configuration.read_text()).get('workspace_api')==1:
        # Keep the read-only operator ledger available for durable reconnection.
        # This daemon starts no VM/model/window at startup; admission still needs
        # a separately chosen live window and current qualification.
        command(['/usr/bin/systemctl','start','mani-vmlab-supervisor.service'],timeout=30)
    return result


def unit_text():
    return '''[Unit]
Description=Bounded Mani inference window and normal model recovery
After=mani-vmlab-supervisor.service

[Service]
Type=notify
ExecStart=/usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/inference_window.py guard
ExecStopPost=/usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/inference_window.py restore
WatchdogSec=10
NotifyAccess=main
RuntimeMaxSec=1830
TimeoutStartSec=180
TimeoutStopSec=240
KillMode=control-group
Restart=no
MemoryMax=128M
TasksMax=32
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/home/mani-vmlab-data/window /run/user/1000/systemd/user.control
ProtectHome=read-only
PrivateTmp=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
LimitCORE=0
UMask=0077
'''
