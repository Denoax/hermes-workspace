"""Fixed per-VM service construction. Values are trusted supervisor generated."""
from pathlib import Path
import re
import uuid

DATA = '/home/mani-vmlab-data'
VM_IDS = ('controller', 'worker_a', 'worker_b')
RUN_ID = re.compile(r'[0-9a-f]{32}\Z')


def unit_name(run_id, vm_id):
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id) or vm_id not in VM_IDS:
        raise ValueError('invalid_owned_VM_identity')
    return f'mani-vmlab-{run_id}-{vm_id}.service'


def qemu_command(vm_id, vm_uuid, artifacts=False):
    if vm_id not in VM_IDS or str(uuid.UUID(vm_uuid)) != vm_uuid:
        raise ValueError('invalid_VM_UUID')
    memory, cpus = (3072, 2) if vm_id == 'controller' else (1536, 1)
    command = ['/usr/bin/qemu-system-x86_64', '-name', 'mani-vmlab-'+vm_id, '-uuid', vm_uuid,
            '-machine', 'q35,accel=kvm,dump-guest-core=off,mem-merge=off', '-cpu', 'host',
            '-m', str(memory), '-smp', str(cpus), '-nodefaults', '-no-user-config',
            '-display', 'none', '-monitor', 'none', '-serial', 'none', '-no-reboot',
            '-sandbox', 'on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny',
            '-object', 'iothread,id=bounded_io,thread-pool-min=0,thread-pool-max=8',
            '-drive', 'file=/vm/disk.qcow2,if=none,id=rootdisk,format=qcow2,cache=none',
            '-device', 'virtio-blk-pci,drive=rootdisk,iothread=bounded_io',
            '-drive', 'file=/vm/seed,if=none,id=seed,format=raw,readonly=on',
            '-device', 'virtio-blk-pci,drive=seed,iothread=bounded_io',
            '-netdev', 'user,id=net0,restrict=on,hostfwd=unix:/control/ssh.sock-:22',
            '-device', 'virtio-net-pci,netdev=net0']
    if artifacts:
        command += ['-drive', 'file=/vm/artifacts,if=none,id=artifacts,format=raw,readonly=on',
                    '-device', 'virtio-blk-pci,drive=artifacts,iothread=bounded_io']
    return command


def service_text(run_id, vm_id, vm_uuid, runtime_seconds, artifacts=False):
    name = unit_name(run_id, vm_id)
    if type(runtime_seconds) is not int or not 1 <= runtime_seconds <= 5400:
        raise ValueError('invalid_absolute_runtime_budget')
    disk = f'{DATA}/runs/{run_id}/{vm_id}.qcow2'
    seed = f'{DATA}/runs/{run_id}/{vm_id}.seed'
    control = f'{DATA}/runs/{run_id}/{vm_id}-control'
    memory = 4*1024 if vm_id == 'controller' else 2304
    command = ' '.join(qemu_command(vm_id, vm_uuid, artifacts))
    artifact_bind = f' {DATA}/artifacts/runtime.iso:/vm/artifacts' if artifacts else ''
    return f'''[Unit]
Description=Owned no-agent Mani lab VM {name}
BindsTo=mani-vmlab-supervisor.service
After=mani-vmlab-supervisor.service

[Service]
Type=exec
User=mani-vmlab-vm
Group=mani-vmlab-vm
SupplementaryGroups=kvm
RootDirectory={DATA}/runtime-root
MountAPIVFS=yes
BindReadOnlyPaths=/usr {DATA}/bases/noble.qcow2:/bases/noble.qcow2 {seed}:/vm/seed{artifact_bind}
BindPaths=/dev/kvm {disk}:/vm/disk.qcow2 {control}:/control
WorkingDirectory=/vm
ExecStartPre=/usr/bin/qemu-img create -f qcow2 -F qcow2 -b /bases/noble.qcow2 /vm/disk.qcow2
ExecStart={command}
PrivateNetwork=yes
PrivateIPC=yes
PrivateDevices=yes
ProtectHome=yes
ProtectSystem=strict
ProtectProc=invisible
ReadWritePaths=/vm/disk.qcow2 /control
DevicePolicy=closed
DeviceAllow=/dev/kvm rw
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
RestrictSUIDSGID=yes
RestrictNamespaces=yes
RestrictRealtime=yes
LockPersonality=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax={memory}M
MemorySwapMax=0
TasksMax=64
CPUQuota=200%
IOWeight=10
IOReadBandwidthMax=/dev/nvme0n1 128M
IOWriteBandwidthMax=/dev/nvme0n1 64M
LimitFSIZE=8G
LimitCORE=0
LimitNOFILE=256
RuntimeMaxSec={runtime_seconds}
TimeoutStopSec=2
KillMode=control-group
Restart=no
StandardOutput=null
StandardError=journal
UMask=0077
'''
