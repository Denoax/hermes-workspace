"""Local operator channel to the fixed native supervisor; never guest exposed."""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import array
from starter.json_limits import bounded_json

CONTROL = Path('/run/mani-vmlab/control.sock')
OPERATIONS = frozenset({'status', 'provision', 'qualify', 'heartbeat', 'stop', 'cleanup', 'run_case',
                        'prepare_model', 'window_heartbeat','workspace_submit','workspace_read','workspace_cancel',
                        'chat_admit','chat_heartbeat','chat_release','chat_cancel'})


def request_schema(operation, run_id=None, vm_id=None, case_id=None, arm=None, version=None, job_id=None, payload=None):
    if type(operation) is not str or operation not in OPERATIONS:
        raise ValueError('unknown_native_operation')
    data = {'operation': operation}
    if operation.startswith('chat_'):
        from lab.text_contract import request
        if any(x is not None for x in (run_id,vm_id,case_id,version,payload)):
            raise ValueError('unexpected_text_admission_fields')
        return request(operation,job_id,arm)
    if operation.startswith('workspace_'):
        from lab.workspace_contract import canonical_id,submit
        if type(version) is not int or version!=1 or any(x is not None for x in (run_id,vm_id,case_id,arm)):
            raise ValueError('versioned_workspace_contract_required')
        data['version']=1
        if operation=='workspace_submit':
            if job_id is not None:raise ValueError('unexpected_job_selector')
            data['payload']=submit(payload)
        else:
            if payload is not None:raise ValueError('unexpected_workspace_payload')
            data['job_id']=canonical_id(job_id)
        return data
    if any(x is not None for x in (version,job_id,payload)):raise ValueError('unexpected_workspace_fields')
    if run_id is not None:
        from lab.state import RUN_ID
        if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
            raise ValueError('invalid_native_run_id')
        data['run_id'] = run_id
    if vm_id is not None:
        from lab.transport import VM_IDS
        if vm_id not in VM_IDS:
            raise ValueError('unknown_native_VM')
        data['vm_id'] = vm_id
    if case_id is not None:
        if case_id not in [f'B{i:02}' for i in range(1, 13)]:
            raise ValueError('unknown_native_case')
        data['case_id'] = case_id
    if arm is not None:
        if arm not in ('normal', 'abliterated'):
            raise ValueError('unapproved_model_arm')
        data['arm'] = arm
    return data


class NativeClient:
    def __init__(self, timeout=60):
        self.timeout = timeout

    def available(self):
        try:
            metadata = CONTROL.lstat()
            parent = CONTROL.parent.lstat()
            return stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == 0 and parent.st_uid == 0 and not parent.st_mode & 0o022
        except FileNotFoundError:
            return False

    def call(self, operation, **fields):
        if operation=='chat_admit':
            raise ValueError('text_admission_requires_descriptor_receiver')
        data = request_schema(operation, **fields)
        if not self.available():
            raise RuntimeError('protected_native_supervisor_not_installed_or_running')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(CONTROL))
            peer_pid, peer_uid, peer_gid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer_uid != 0:
                raise PermissionError('native_supervisor_peer_not_root')
            connection.sendall(json.dumps(data).encode() + b'\n')
            connection.shutdown(socket.SHUT_WR)
            raw = bytearray()
            while chunk := connection.recv(8192):
                raw.extend(chunk)
                if len(raw) > 262144:
                    raise ValueError('native_reply_limit')
            result = bounded_json(bytes(raw), max_bytes=262144)
            if type(result) is not dict or result.get('status') not in ('ok', 'blocked', 'failed'):
                raise ValueError('invalid_native_reply')
            return result

    def text_connection(self, job_id, arm):
        """Receive only a root-attested connected socket, never a path or URL."""
        data=request_schema('chat_admit',job_id=job_id,arm=arm)
        if not self.available():raise RuntimeError('protected_text_admission_not_installed')
        descriptors=[]
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as channel:
                channel.settimeout(self.timeout);channel.connect(str(CONTROL))
                if struct.unpack('3i',channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]!=0:
                    raise PermissionError('native_supervisor_peer_not_root')
                channel.sendall(json.dumps(data).encode());channel.shutdown(socket.SHUT_WR)
                raw=bytearray()
                while True:
                    part,ancillary,flags,_=channel.recvmsg(8192,socket.CMSG_SPACE(4*4),socket.MSG_CMSG_CLOEXEC)
                    for level,kind,rights in ancillary:
                        if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                            found=array.array('i');found.frombytes(rights[:len(rights)-len(rights)%found.itemsize]);descriptors.extend(found)
                    if flags&socket.MSG_CTRUNC:raise RuntimeError('native_descriptor_truncated')
                    if not part:break
                    raw.extend(part)
                    if len(raw)>65536:raise ValueError('native_text_reply_limit')
                if not raw:
                    raise RuntimeError('Protected model admission closed without a receipt. Check the native service and normal Qwen recovery, then retry this turn.')
                try:
                    result=bounded_json(bytes(raw),max_bytes=65536)
                except ValueError:
                    raise RuntimeError('Protected model admission returned an invalid receipt. Check the native service log and normal Qwen recovery, then retry this turn.') from None
                if type(result) is not dict or result.get('status') not in ('ok','blocked','failed'):
                    raise RuntimeError('Protected model admission returned an invalid receipt. Check the native service log and normal Qwen recovery, then retry this turn.')
                if result.get('status')!='ok' or len(descriptors)!=1:
                    raise RuntimeError(result.get('error','native_text_admission_denied'))
                # Retain ownership until construction succeeds; a malformed
                # receipt must not leak an admitted non-socket descriptor.
                connection=socket.socket(fileno=descriptors[-1]);descriptors.pop()
                return result,connection
        finally:
            for descriptor in descriptors:os.close(descriptor)


def public_snapshot():
    path=Path('/var/lib/mani-vmlab-review/status-public.json')
    try:
        parent=path.parent.lstat();metadata=path.lstat()
        if parent.st_uid!=0 or parent.st_mode&0o022 or metadata.st_uid!=0 or metadata.st_mode&0o022 or not stat.S_ISREG(metadata.st_mode):
            raise PermissionError('protected_status_snapshot_required')
        descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(descriptor,'rb') as source:
            raw=source.read(65537)
            if os.fstat(source.fileno()).st_ino!=metadata.st_ino:raise RuntimeError('status_snapshot_changed')
        data=bounded_json(raw,max_bytes=65536)
        if data.get('boot_id')!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():
            return {'status':'closed','ledger':'native_root_owned_historical','reason':'snapshot_from_previous_boot','historical':data}
        return data
    except FileNotFoundError:
        return {'status':'closed','ledger':'native_root_owned','reason':'protected_native_status_snapshot_unavailable'}
