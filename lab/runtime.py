"""Fixed QEMU argument construction and pinned overlay preparation.

Launching needs an independently reviewed installed confined system service.
The desktop UID is deliberately never used to launch QEMU by this module.
"""
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from lab.doctor import verify_artifact
from lab.transport import VM_IDS


def qemu_argv(vm_id, overlay, seed, control_port, vm_uuid):
    if vm_id not in VM_IDS or str(uuid.UUID(vm_uuid)) != vm_uuid:
        raise ValueError("invalid_VM_identity")
    if type(control_port) is not int or not 1024 <= control_port <= 65535:
        raise ValueError("invalid_control_port")
    paths = (Path(overlay), Path(seed))
    if any(not p.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(p)) for p in paths):
        raise ValueError("unsafe_QEMU_option_path")
    memory, cpus = (3072, 2) if vm_id == "controller" else (1536, 1)
    return ["/usr/bin/qemu-system-x86_64", "-name", "mani-vmlab-" + vm_id,
            "-uuid", vm_uuid, "-machine", "q35,accel=kvm,dump-guest-core=off,mem-merge=off",
            "-cpu", "host", "-m", str(memory), "-smp", str(cpus),
            "-nodefaults", "-no-user-config", "-display", "none", "-monitor", "none",
            "-serial", "none", "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
            "-drive", f"file={paths[0]},if=virtio,format=qcow2,cache=none",
            "-drive", f"file={paths[1]},if=virtio,format=raw,readonly=on",
            "-netdev", f"user,id=net0,restrict=on,hostfwd=tcp:127.0.0.1:{control_port}-:22",
            "-device", "virtio-net-pci,netdev=net0", "-no-reboot"]


def prepare_overlays(store, run_id, image_pin, dry_run=False):
    verification = verify_artifact(image_pin)
    executable = shutil.which("qemu-img")
    names = [vm_id + ".qcow2" for vm_id in VM_IDS]
    if dry_run:
        return {"dry_run": True, "image": verification, "overlays": names, "qemu_img_available": bool(executable)}
    if not executable:
        raise RuntimeError("qemu_img_missing")
    for name in names:
        target = store.directory(run_id) / name
        if target.exists():
            registered = store.read(run_id)["resources"]
            if not any(r["name"] == name for r in registered):
                raise RuntimeError("refuse_existing_unregistered_overlay")
            continue
        subprocess.run([executable, "create", "-f", "qcow2", "-F", "qcow2", "-b",
                        str(Path(image_pin["path"]).resolve()), str(target)],
                       check=True, capture_output=True, timeout=30)
        target.chmod(0o600)
        store.register_resource(run_id, name)
    return {"image": verification, "overlays": names}
