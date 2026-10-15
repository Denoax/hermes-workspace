"""Private durable run ledger with one writer lock and registered resources."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
import uuid

RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
RESOURCE = re.compile(r"(?:controller|worker_a|worker_b)(?:\.(?:qcow2|seed|sock|key(?:\.pub)?|pub|known_hosts)|-host\.key(?:\.pub)?|-user-data)\Z")


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, sort_keys=True, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class RunStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("state_root_must_be_private_owned_directory")

    def directory(self, run_id):
        if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
            raise ValueError("invalid_run_id")
        path = self.root / run_id
        if path.is_symlink():
            raise ValueError("unsafe_run_directory")
        if path.exists():
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("unsafe_run_directory")
        return path

    @contextmanager
    def locked(self, run_id):
        directory = self.directory(run_id)
        fd = os.open(directory / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield directory
        finally:
            os.close(fd)

    def create(self, ttl=480, heartbeat_timeout=45, max_calls=24, max_tokens=24576):
        if type(ttl) not in (float, int) or not 0 < ttl <= 5400:
            raise ValueError("invalid_ttl")
        if type(heartbeat_timeout) not in (float, int) or not 0 < heartbeat_timeout <= ttl:
            raise ValueError("invalid_heartbeat_timeout")
        if type(max_calls) is not int or not 1 <= max_calls <= 288:
            raise ValueError("invalid_call_budget")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 294912:
            raise ValueError("invalid_token_budget")
        run_id = uuid.uuid4().hex
        directory = self.directory(run_id)
        directory.mkdir(mode=0o700)
        now = time.monotonic()
        manifest = {
            "run_id": run_id, "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "issued": now, "deadline": now + ttl, "heartbeat": now,
            "heartbeat_timeout": heartbeat_timeout, "last_clock": now,
            "max_calls": max_calls, "calls": 0, "tokens_reserved": 0,
            "max_tokens": max_tokens, "jobs": [], "processes": [], "resources": [],
            "status": "active", "reason": None, "execution_kind": "control_integration",
        }
        atomic_json(directory / "manifest.json", manifest)
        atomic_json(directory / "secret.json", {"token": secrets.token_urlsafe(32)})
        return run_id

    def read(self, run_id):
        return json.loads((self.directory(run_id) / "manifest.json").read_text())

    def token(self, run_id):
        return json.loads((self.directory(run_id) / "secret.json").read_text())["token"]

    def mutate(self, run_id, operation):
        with self.locked(run_id) as directory:
            manifest = self.read(run_id)
            result = operation(manifest)
            atomic_json(directory / "manifest.json", manifest)
            return result

    @staticmethod
    def active(manifest, now=None):
        now = time.monotonic() if now is None else now
        if manifest["status"] != "active":
            return manifest["reason"] or "revoked"
        current_boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        reason = None
        if current_boot != manifest["boot_id"]:
            reason = "host_reboot"
        elif type(now) not in (float, int) or not manifest["last_clock"] <= now < float("inf"):
            reason = "invalid_or_regressed_host_clock"
        elif now >= manifest["deadline"]:
            reason = "absolute_expiry"
        elif now - manifest["heartbeat"] >= manifest["heartbeat_timeout"]:
            reason = "heartbeat_lost"
        if reason:
            manifest.update(status="revoked", reason=reason)
        else:
            manifest["last_clock"] = now
        return reason

    def heartbeat(self, run_id):
        def update(manifest):
            if self.active(manifest):
                return False
            manifest["heartbeat"] = time.monotonic()
            return True
        return self.mutate(run_id, update)

    def admit(self, run_id, token, job_id, output_tokens):
        if type(job_id) is not str or not RUN_ID.fullmatch(job_id):
            return "invalid_job_id"
        if type(output_tokens) is not int or not 1 <= output_tokens <= 1024:
            return "invalid_output_budget"
        def check(manifest):
            reason = self.active(manifest)
            if reason:
                return reason
            if type(token) is not str or not secrets.compare_digest(token, self.token(run_id)):
                return "invalid_token"
            if job_id in manifest["jobs"]:
                return "reject_duplicate"
            if manifest["calls"] >= manifest["max_calls"]:
                return "call_budget_exhausted"
            if manifest["tokens_reserved"] + output_tokens > manifest["max_tokens"]:
                return "token_budget_exhausted"
            # Failed/admitted attempts retain their reservations; retries cannot refund them.
            manifest["calls"] += 1
            manifest["tokens_reserved"] += output_tokens
            manifest["jobs"].append(job_id)
            return None
        return self.mutate(run_id, check)

    def revoke(self, run_id, reason):
        def update(manifest):
            if manifest["status"] == "active":
                manifest.update(status="revoked", reason=reason)
        self.mutate(run_id, update)

    def register_resource(self, run_id, name):
        if not RESOURCE.fullmatch(name):
            raise ValueError("unregistered_resource_type")
        path = self.directory(run_id) / name
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise ValueError("resource_must_be_regular_file")
        record = {"name": name, "device": info.st_dev, "inode": info.st_ino}
        def update(manifest):
            if self.active(manifest):
                raise ValueError("run_inactive")
            if any(r["name"] == name for r in manifest["resources"]):
                raise ValueError("duplicate_resource")
            manifest["resources"].append(record)
        self.mutate(run_id, update)

    def cleanup(self, run_id, process_stopper, dry_run=False):
        manifest = self.read(run_id)
        if dry_run:
            return {"dry_run": True, "registered_resources": [r["name"] for r in manifest["resources"]]}
        self.revoke(run_id, "operator_cleanup")
        outcomes = process_stopper(self, run_id) or []
        if any(item["outcome"] == "termination_unconfirmed" for item in outcomes):
            raise RuntimeError("refuse_cleanup_while_owned_process_may_be_active")
        removed, refused = [], []
        with self.locked(run_id) as directory:
            manifest = self.read(run_id)
            for resource in manifest["resources"]:
                name = resource["name"]
                if not RESOURCE.fullmatch(name):
                    refused.append("invalid_resource_name")
                    continue
                path = directory / name
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == (resource["device"], resource["inode"]):
                    path.unlink()
                    removed.append(name)
                else:
                    refused.append(name)
            # This file is created only by create(), and contains no reusable credentials.
            (directory / "secret.json").unlink(missing_ok=True)
            manifest["cleanup"] = {"removed": removed, "refused": refused}
            atomic_json(directory / "manifest.json", manifest)
        return manifest["cleanup"]
