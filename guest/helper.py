"""Fixed guest SSH ForceCommand helper. Host passes bounded JSON through stdin."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from json_limits import bounded_json


def main():
    if os.geteuid() == 0 or not Path("/etc/mani-vmlab/guest.json").is_file():
        raise RuntimeError("guest_only_nonroot_helper")
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError("request_limit")
    data = bounded_json(raw, max_bytes=32768)
    if type(data) is not dict or set(data) - {"action", "job_id", "case"} or not {"action", "job_id"} <= set(data):
        raise ValueError("invalid_helper_schema")
    resource.setrlimit(resource.RLIMIT_CPU, (450, 450))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    if data["action"] == "health" and set(data) == {"action", "job_id"}:
        print(json.dumps({"healthy": True, "role": json.loads(Path("/etc/mani-vmlab/guest.json").read_text())["role"]}))
        return
    if data["action"] != "solve" or set(data) != {"action", "job_id", "case"}:
        raise ValueError("unknown_or_unimplemented_guest_action")
    case = data["case"]
    if type(case) is not dict or set(case) != {"prompt", "model", "relay_token"}:
        raise ValueError("invalid_case_payload")
    # No candidate executable, shell, path or supervisor action comes from the agent.
    result = subprocess.run(["/opt/hermes/.venv/bin/python", "-B", "/opt/mani-vmlab/solve.py"],
                            input=json.dumps(case).encode(), capture_output=True, timeout=480,
                            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    if result.returncode:
        raise RuntimeError("guest_Hermes_failed")
    if len(result.stdout) > 65536:
        raise RuntimeError("guest_answer_limit")
    sys.stdout.buffer.write(result.stdout)


if __name__ == "__main__":
    main()
