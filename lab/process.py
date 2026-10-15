"""Linux pidfd lifecycle operations. Never select processes by executable name."""
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time


def identity(pid):
    if type(pid) is not int or pid <= 1:
        raise ValueError("invalid_pid")
    # comm may contain spaces and closing parentheses; only the final ')' ends it.
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": int(fields[19]),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def open_owned(record):
    if not hasattr(os, "pidfd_open"):
        raise RuntimeError("pidfd_required")
    try:
        fd = os.pidfd_open(record["pid"])
        if identity(record["pid"]) != {k: record[k] for k in ("pid", "start_ticks", "boot_id")}:
            os.close(fd)
            return None
        return fd
    except ProcessLookupError:
        return None
    except FileNotFoundError:
        return None


def register(store, run_id, process, role):
    record = {**identity(process.pid), "role": role}
    def update(manifest):
        if store.active(manifest):
            raise RuntimeError("run_inactive")
        manifest["processes"].append(record)
    try:
        store.mutate(run_id, update)
    except BaseException:
        process.kill()
        process.wait()
        raise
    return record


def stop_owned(store, run_id, grace=0.2):
    records = store.read(run_id)["processes"]
    outcomes = []
    handles = []
    for record in records:
        fd = open_owned(record)
        if fd is None:
            outcomes.append({"role": record["role"], "outcome": "absent_or_identity_mismatch"})
            continue
        try:
            signal.pidfd_send_signal(fd, signal.SIGTERM)
            handles.append((record, fd))
        except ProcessLookupError:
            os.close(fd)
    # Bound the whole fleet grace, rather than multiplying it by guest count.
    deadline = time.monotonic() + grace
    try:
        for record, fd in handles:
            readable, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
            if not readable:
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                readable, _, _ = select.select([fd], [], [], 1)
            outcomes.append({"role": record["role"], "outcome":
                             "stopped_exact_identity" if readable else "termination_unconfirmed"})
    finally:
        for _, fd in handles:
            os.close(fd)
    store.mutate(run_id, lambda m: m.update(stop_outcomes=outcomes))
    return outcomes


def start_watchdog(store, run_id, owner_pid=None):
    owner = identity(os.getpid() if owner_pid is None else owner_pid)
    store.mutate(run_id, lambda m: m.update(owner=owner))
    # No inherited terminal, environment credentials, or output containing tokens.
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "lab.watchdog", str(store.root), run_id],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, env=environment,
    )
    # The watchdog is independent and must never be among the fleet it stops.
    store.mutate(run_id, lambda m: m.update(watchdog=identity(process.pid)))
    return process
