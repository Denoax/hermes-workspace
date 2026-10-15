"""Cheap drift-sensitive status proofs; admissions perform explicit revalidation."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import threading


def identity(path):
    info=Path(path).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise PermissionError('protected_immutable_artifact_required')
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns


class PinnedImage:
    def __init__(self,path,expected):
        self.path=Path(path);self.expected=expected;self.verified=None;self.full_hashes=0

    def current(self):
        try:return self.verified is not None and identity(self.path)==self.verified
        except (OSError,PermissionError):return False

    def verify(self):
        before=identity(self.path)
        if before==self.verified:return True
        digest=hashlib.sha256()
        with self.path.open('rb') as source:
            while chunk:=source.read(4*1024*1024):digest.update(chunk)
        self.full_hashes+=1
        if identity(self.path)!=before or digest.hexdigest()!=self.expected:
            self.verified=None;raise ValueError('base_image_pin_or_identity_changed')
        self.verified=before;return True


def bunker_policy(rules):
    chains=[item.get('chain',{}) for item in rules]
    return all(any(chain.get('family')=='inet' and chain.get('table')=='mani_pc_bunker'
        and chain.get('name')==name and chain.get('hook')==hook and chain.get('type')=='filter'
        and chain.get('policy')=='drop' and type(chain.get('prio')) is int
        for chain in chains) for name,hook in [('input','input'),('forward_guard','forward')])


class Firewall:
    def __init__(self):
        self.valid=False;self.dirty=True;self.inspections=0;self.lock=threading.Lock()
        self.monitor=None;self.configuration=None;self.owner_identity=None
        self.owner=Path('/etc/systemd/system/mani-pc-bunker.service')
        self.owner_sha='6b5bd14e0d9faa4bc91c56150cbad942852a941293543a3c761a7a2890d4075d'

    def start_monitor(self):
        parent=os.getpid()
        self.monitor=subprocess.Popen(['/usr/bin/python3','-I','/usr/local/lib/mani-vmlab/nft_monitor.py',str(parent)],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C'})
        def watch():
            try:
                while self.monitor.stdout.read1(4096):
                    with self.lock:self.dirty=True
            finally:
                with self.lock:self.valid=False;self.dirty=True
        threading.Thread(target=watch,daemon=True).start()

    def current(self):
        with self.lock:
            try:owner_current=self.owner_identity==identity(self.owner)
            except (OSError,PermissionError):owner_current=False
            return self.current_unlocked() and owner_current

    def verify(self):
        with self.lock:
            owner=identity(self.owner)
            if self.current_unlocked() and self.owner_identity==owner:return True
            if hashlib.sha256(self.owner.read_bytes()).hexdigest()!=self.owner_sha:
                raise RuntimeError('PC_Bunker_owner_unit_drift_review_required')
            reply=subprocess.run(['/usr/bin/nft','-j','list','table','inet','mani_pc_bunker'],
                stdin=subprocess.DEVNULL,capture_output=True,timeout=5,env={'PATH':'/usr/bin:/bin','LANG':'C'})
            self.inspections+=1
            if reply.returncode or len(reply.stdout)>262144:raise RuntimeError('expected_PC_Bunker_table_unavailable')
            self.valid=bunker_policy(json.loads(reply.stdout)['nftables'])
            if not self.valid:raise RuntimeError('expected_PC_Bunker_hooks_not_qualified')
            # Exact owner/table/type/hooks are required. The hash records this
            # current kernel table, rather than unrelated drop-chain presence.
            self.configuration=hashlib.sha256(reply.stdout).hexdigest()
            self.dirty=False
            self.owner_identity=owner
            return True

    def current_unlocked(self):
        return self.valid and not self.dirty and self.monitor is not None and self.monitor.poll() is None

    def close(self):
        if self.monitor:
            self.monitor.terminate();self.monitor.wait(timeout=3);self.monitor.stdout.close()
