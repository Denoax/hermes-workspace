"""One confined owned model process, Unix-only API and bounded GPU compute."""
import http.client
import fcntl
import json
import hashlib
import os
import pwd
from pathlib import Path
import socket
import stat
import subprocess
import time

DATA = Path('/home/mani-vmlab-data')
ALIAS = 'mani-lab-qwen'
UNIT = 'mani-vmlab-backend.service'
SOCKET = DATA/'backend-control/backend.sock'
GPU_DEVICES = ('/dev/nvidia0', '/dev/nvidiactl', '/dev/nvidia-uvm', '/dev/nvidia-uvm-tools',
               '/dev/dri/renderD128', '/dev/dri/renderD129')
ARTIFACT_LOCK=Path('/usr/local/lib/mani-vmlab-setup/backend-artifacts.lock.json')
ARTIFACT_LOCK_SHA='560a28dbe71b021887a8d6d546a4c128cd02ee99e8bce67a4ace506e5a7e19fa'
ARTIFACT_PROOF=DATA/'artifact-proof.json'


def artifact_inventory():
    from evidence import identity
    identity(ARTIFACT_LOCK)
    raw=ARTIFACT_LOCK.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ARTIFACT_LOCK_SHA:raise RuntimeError('approved_artifact_lock_required')
    lock=json.loads(raw)
    return [(DATA/'models'/(arm+'.gguf'),item) for arm,item in lock['models'].items()]+[(DATA/'backend-b9980'/item['name'],item) for item in lock['backend_files']]


def verify_artifacts():
    from evidence import identity
    from lab.state import atomic_json
    rows=[];started=time.monotonic()
    for path,item in artifact_inventory():
        before=identity(path)
        with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
        if identity(path)!=before or before[2]!=item['bytes'] or digest!=item['sha256']:raise RuntimeError('pinned_model_or_backend_artifact_changed')
        rows.append({'path':str(path),'identity':list(before),'sha256':digest})
    proof={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'lock_sha256':ARTIFACT_LOCK_SHA,
        'files':rows,'full_verification_wall_seconds':time.monotonic()-started}
    atomic_json(ARTIFACT_PROOF,proof)
    return {'verified_files':len(rows),'models':{path.stem:item['sha256'] for path,item in artifact_inventory() if path.suffix=='.gguf'},
        'full_verification_wall_seconds':proof['full_verification_wall_seconds'],'status_polling_hashes':0}


def artifacts_current():
    from evidence import identity
    try:
        identity(ARTIFACT_PROOF)
        proof=json.loads(ARTIFACT_PROOF.read_text())
        expected=artifact_inventory()
        if proof['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip() or proof['lock_sha256']!=ARTIFACT_LOCK_SHA:return False
        rows={item['path']:item for item in proof['files']}
        return len(rows)==len(expected) and all(rows.get(str(path),{}).get('identity')==list(identity(path)) and rows[str(path)]['sha256']==item['sha256'] for path,item in expected)
    except (OSError,ValueError,KeyError,RuntimeError):return False


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, timeout=5):
        super().__init__('localhost', timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(SOCKET))


def get(path):
    connection = UnixHTTP()
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        raw = response.read(32769)
        if response.status != 200 or len(raw) > 32768:
            raise RuntimeError('backend_health_or_limit')
        return json.loads(raw)
    finally:
        connection.close()


def unit_text(arm):
    if arm not in ('normal', 'abliterated'):
        raise ValueError('pinned_model_arm_required')
    binds = ' '.join(GPU_DEVICES)
    allows = '\n'.join('DeviceAllow='+name+' rw' for name in GPU_DEVICES)
    return f'''[Unit]
Description=Owned isolated Mani model backend ({arm})
BindsTo=mani-vmlab-supervisor.service mani-vmlab-inference-window.service
After=mani-vmlab-supervisor.service mani-vmlab-inference-window.service

[Service]
Type=exec
User=mani-vmlab-model
Group=mani-vmlab-model
RootDirectory={DATA}/backend-root
MountAPIVFS=yes
BindReadOnlyPaths=/usr {DATA}/backend-b9980:/backend {DATA}/models/{arm}.gguf:/model/weights.gguf
BindPaths={binds} {DATA}/backend-control:/control
ExecStart=/backend/llama-server --model /model/weights.gguf --alias {ALIAS} --host /control/backend.sock --port 18082 --ctx-size 8192 --parallel 1 --n-gpu-layers 99 --n-cpu-moe 28 --device Vulkan0 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --threads 8 --threads-batch 14 --threads-http 2 --jinja --reasoning-preserve --no-webui --fit off
Environment=HOME=/nonexistent LD_LIBRARY_PATH=/backend
WorkingDirectory=/backend
PrivateNetwork=yes
PrivateIPC=yes
PrivateDevices=yes
ProtectHome=yes
ProtectSystem=strict
ProtectProc=invisible
ReadWritePaths=/control
DevicePolicy=closed
{allows}
CapabilityBoundingSet=
AmbientCapabilities=
NoNewPrivileges=yes
RestrictNamespaces=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
MemoryMax=32G
MemorySwapMax=0
CPUQuota=1000%
TasksMax=256
IOReadBandwidthMax=/dev/nvme0n1 128M
IOWriteBandwidthMax=/dev/nvme0n1 32M
RuntimeMaxSec=900
TimeoutStopSec=2
KillMode=control-group
Restart=no
LimitCORE=0
LimitNOFILE=256
UMask=0077
'''


def stop():
    # Relay timeout, transport failure and outside teardown can coincide.
    # This root-private lock spans threads and trusted control processes.
    with (DATA/'window/backend-stop.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        _stop_locked()


def _stop_locked():
    load = subprocess.check_output(['/usr/bin/systemctl', 'show', UNIT, '-p', 'LoadState', '--value'], timeout=5)
    if load.strip() == b'not-found':
        return
    subprocess.run(['/usr/bin/systemctl', 'stop', UNIT], check=True, timeout=10, capture_output=True)
    if SOCKET.exists():
        info = SOCKET.lstat()
        import stat
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != pwd.getpwnam('mani-vmlab-model').pw_uid:
            raise RuntimeError('preserve_unexpected_backend_socket')
        SOCKET.unlink(missing_ok=True)


def _write_unit(path, arm):
    """Preserve unknown files and set the static generated unit's own mode.

    The supervisor's private umask must not change the registered0644 unit
    contract. Read/validate an existing file before any write or mode change.
    """
    raw = unit_text(arm).encode()
    known = (unit_text('normal').encode(), unit_text('abliterated').encode())
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o644)
        before = None
    except FileExistsError:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != os.geteuid():
            raise RuntimeError('preserve_unregistered_backend_unit')
        descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'r+b') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise RuntimeError('preserve_unregistered_backend_unit')
        if before is not None:
            identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
            if identity(info) != identity(before) or stream.read(max(map(len, known)) + 1) not in known:
                raise RuntimeError('preserve_unregistered_backend_unit')
            if identity(os.fstat(stream.fileno())) != identity(info):
                raise RuntimeError('preserve_changed_backend_unit')
        os.fchmod(stream.fileno(), 0o644)
        stream.seek(0)
        stream.write(raw)
        stream.truncate()


def start(arm, valid=lambda:True):
    import window
    if not window.active() or not valid():
        raise RuntimeError('chosen_inference_window_required')
    if not artifacts_current():raise RuntimeError('fresh_pinned_artifact_verification_required')
    stop()
    path = Path('/run/systemd/system')/UNIT
    _write_unit(path, arm)
    subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True, timeout=10, capture_output=True)
    subprocess.run(['/usr/bin/systemctl', 'start', UNIT], check=True, timeout=30, capture_output=True)
    started = time.monotonic()
    while time.monotonic()-started < 300:
        if not window.active() or not valid():
            stop()
            raise RuntimeError('inference_window_expired_during_load')
        try:
            if get('/health').get('status') == 'ok':
                props = get('/props')
                if props['model_alias'] != ALIAS or props['default_generation_settings']['n_ctx'] != 8192:
                    raise RuntimeError('loaded_backend_configuration_changed')
                return {'arm':arm, 'load_wall_seconds':time.monotonic()-started,
                        'context':8192, 'model_alias':ALIAS, 'build':props['build_info']}
        except (OSError, ValueError, http.client.HTTPException, RuntimeError):
            pass
        time.sleep(0.2)
    stop()
    raise TimeoutError('dedicated_backend_load_timeout')


def resources():
    pid = int(subprocess.check_output(['/usr/bin/systemctl','show',UNIT,'-p','MainPID','--value'],timeout=5))
    status = Path(f'/proc/{pid}/status').read_text().splitlines()
    return {'backend_PID':pid, 'RSS_high_water_kib':int(next(x for x in status if x.startswith('VmHWM:')).split()[1]),
        'device_aggregate_VRAM_MiB':int(subprocess.check_output(['/usr/bin/nvidia-smi',
            '--query-gpu=memory.used','--format=csv,noheader,nounits'],timeout=5).strip()),
        'VRAM_scope':'whole_device_including_desktop; sample, not continuous peak'}


def qualify(arm):
    pid = int(subprocess.check_output(['/usr/bin/systemctl','show',UNIT,'-p','MainPID','--value'],timeout=5))
    root = Path(f'/proc/{pid}/root')
    status = Path(f'/proc/{pid}/status').read_text().splitlines()
    model_uid = pwd.getpwnam('mani-vmlab-model').pw_uid
    facts = {'nonroot_separate_model_UID':model_uid != 0 and model_uid != pwd.getpwnam('mani-vmlab-vm').pw_uid
        and int(next(x for x in status if x.startswith('Uid:')).split()[1]) == model_uid,
        'personal_home_absent':not (root/'home/mani').exists(),
        'Docker_socket_absent':not (root/'run/docker.sock').exists(),
        'private_network':os.readlink(f'/proc/{pid}/ns/net')!=os.readlink('/proc/self/ns/net'),
        'private_IPC':os.readlink(f'/proc/{pid}/ns/ipc')!=os.readlink('/proc/self/ns/ipc'),
        'capabilities_empty':int(next(x for x in status if x.startswith('CapEff:')).split()[1],16)==0}
    tokens = {}
    for add_special in (False, True):
        connection = UnixHTTP()
        try:
            connection.request('POST','/tokenize',json.dumps({'content':'Tokenizer compatibility probe','add_special':add_special}),
                               {'Content-Type':'application/json'})
            response=connection.getresponse()
            if response.status!=200:raise RuntimeError('runtime_tokenizer_probe_failed')
            tokens[str(add_special)] = json.loads(response.read(8192))['tokens']
        finally:
            connection.close()
    return {'confined':all(facts.values()), 'facts':facts, 'effective_tokenizer_probe':tokens,
            'arm':arm, 'resources':resources(), 'endpoint':'owned_Unix_socket_only',
            'weights_and_runtime':'protected_host_hash_verified_read_only_binds'}
