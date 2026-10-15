"""Read-only feasibility checks. No service reload, inference or credential reads."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from lab.native_client import NativeClient
from lab.readiness import stage_results


def command(argv, timeout=10):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"exit": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit": None, "error": type(exc).__name__}


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as source:
        while data := source.read(4 * 1024 * 1024):
            checksum.update(data)
    return checksum.hexdigest()


def inspect():
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            mem[key + "_bytes"] = int(value.split()[0]) * 1024
    cpu = Path("/proc/cpuinfo").read_text()
    hardware = {
        "cpu_count": os.cpu_count(), "virtualization_flag": " vmx " in cpu or " svm " in cpu,
        "memory": mem, "home_available_bytes": shutil.disk_usage(Path.home()).free,
        "root_available_bytes": shutil.disk_usage("/").free,
        "gpu": command(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"]),
    }
    tools = {name: shutil.which(name) for name in ("qemu-system-x86_64", "qemu-img", "cloud-localds", "ssh", "systemctl")}
    checks = {
        "kvm_rw": os.access("/dev/kvm", os.R_OK | os.W_OK),
        "qemu_installed": tools["qemu-system-x86_64"] is not None and tools["qemu-img"] is not None,
        "native_admin_cached": command(["sudo", "-n", "true"])["exit"] == 0,
        "system_jobs": command(["systemctl", "list-jobs", "--no-legend", "--no-pager"]),
        "firewall_manager": command(["systemctl", "is-active", "nftables", "firewalld", "ufw"]),
        "normal_services": command(["systemctl", "--user", "show", "manibot-llama.service",
                                    "hermes-gateway.service", "-p", "ActiveState", "-p", "SubState", "-p", "MainPID"]),
    }
    client = NativeClient(timeout=3)
    native = client.call('status') if client.available() else {'status': 'blocked', 'reason': 'protected_native_supervisor_missing'}
    facts = {'kvm': checks['kvm_rw'], 'runtime_packages': checks['qemu_installed'] and tools['cloud-localds'] is not None,
             'root_storage_reserve': hardware['root_available_bytes'] >= 2 * 1024**3,
             'memory_reserve': mem['MemAvailable_bytes'] >= 14 * 1024**3,
             'maintenance_idle': checks['system_jobs'].get('exit') == 0 and checks['system_jobs'].get('stdout') == '',
             'protected_supervisor': native['status'] == 'ok'}
    if native['status'] == 'ok':
        supplied = native.get('observed_facts', {})
        if type(supplied) is not dict or any(type(v) is not bool for v in supplied.values()):
            raise ValueError('invalid_native_observations')
        # Fresh observations arrive over root-authenticated IPC, never an editable receipt.
        facts.update(supplied)
    stages = {name: result.as_dict() for name, result in stage_results(facts).items()}
    return {"schema_version": 1, "measured_unix_seconds": time.time(), "hardware": hardware,
            "tools": tools, "checks": checks, 'native': native, 'stages': stages,
            "live_ready": stages['paired']['ready'], "blockers": stages['paired']['missing']}


def verify_artifact(record):
    if type(record) is not dict or not {"path", "sha256", "bytes"} <= set(record):
        raise ValueError("artifact_pin_required")
    path = Path(record["path"])
    if path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]:
        raise ValueError("artifact_size_or_path_mismatch")
    if digest(path) != record["sha256"]:
        raise ValueError("artifact_hash_mismatch")
    return {"bytes": record["bytes"], "sha256": record["sha256"], "verified": True}
