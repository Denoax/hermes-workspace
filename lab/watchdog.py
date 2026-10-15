"""Independent detached enforcement, including dead supervisor recovery."""
from pathlib import Path
import select
import sys
import time
import os
from lab.process import open_owned, stop_owned
from lab.state import RunStore, atomic_json


def watch(store, run_id):
    owner_fd = open_owned(store.read(run_id)["owner"])
    reason = "owner_absent" if owner_fd is None else None
    try:
        while reason is None:
            if select.select([owner_fd], [], [], 0.025)[0]:
                reason = "owner_crashed"
                break
            reason = store.mutate(run_id, lambda m: store.active(m))
        store.revoke(run_id, reason)
        outcomes = stop_owned(store, run_id, grace=0 if reason == "absolute_expiry" else 0.2)
        atomic_json(store.directory(run_id) / "watchdog_result.json", {
            "reason": reason, "stopped_monotonic": time.monotonic(), "outcomes": outcomes,
            "evidence_kind": "real_host_process_control_not_VM_containment",
        })
    finally:
        if owner_fd is not None:
            os.close(owner_fd)


if __name__ == "__main__":
    watch(RunStore(Path(sys.argv[1])), sys.argv[2])
