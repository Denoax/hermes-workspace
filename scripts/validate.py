"""Run existing/new offline tests and optional real owned control integrations."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "results" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    patterns = ["test_starter.py", "test_lab.py", 'test_native_setup.py', 'test_stages.py',
                'test_qualification.py', 'test_execution.py', 'test_maintenance.py', 'test_inference_runtime.py', 'test_receipt.py',
                'test_workspace.py', 'test_recovery_complete.py'] + (["test_integration.py"] if args.integration else [])
    records = []
    for pattern in patterns:
        command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
        started = time.monotonic()
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
        (output / (pattern + ".log")).write_text(result.stdout + result.stderr)
        measurements = [json.loads(line.removeprefix("CONTROL_METRIC ")) for line in result.stdout.splitlines()
                        if line.startswith("CONTROL_METRIC ")]
        record = {"suite": pattern, "command": command[1:], "exit": result.returncode,
                  "wall_seconds": time.monotonic() - started,
                  "evidence_kind": "real_owned_host_process_and_loopback_fixture" if pattern == "test_integration.py" else "offline_unit",
                  "VM_or_model_evidence": False, "measurements": measurements}
        records.append(record)
        print(json.dumps(record))
    (output / "validation.json").write_text(json.dumps(records, indent=2) + "\n")
    return 0 if all(r["exit"] == 0 for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
