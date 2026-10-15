"""Pinned SSH transport to one fixed guest helper; requests use JSON stdin."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
import uuid
from starter.json_limits import bounded_json

VM_IDS = ("controller", "worker_a", "worker_b")


class CommandFailure(RuntimeError):
    """Keep bounded diagnostics private; the public message excludes stderr."""
    def __init__(self, argv, code, errors):
        self.command = Path(argv[0]).name
        self.exit_code = code
        self.private_stderr = bytes(errors).decode(errors='replace')
        super().__init__('guest_transport_failed:'+self.command+':exit='+str(code))


def bounded_process(argv, raw, timeout, pass_fds=()):
    """Bound transport memory before parsing any guest-controlled output."""
    if len(raw) > 65536 or not 0 < timeout <= 480:
        raise ValueError("invalid_transport_budget")
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, close_fds=True,
                               pass_fds=pass_fds,
                               env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    deadline = time.monotonic() + timeout
    output, errors = bytearray(), bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            for stream, mode, label in ((process.stdin, selectors.EVENT_WRITE, "input"),
                                        (process.stdout, selectors.EVENT_READ, "output"),
                                        (process.stderr, selectors.EVENT_READ, "error")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, mode, label)
            position = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("guest_job_timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    stream = key.fileobj
                    if key.data == "input":
                        try:
                            position += os.write(stream.fileno(), raw[position:])
                        except BrokenPipeError:
                            position = len(raw)
                        if position == len(raw):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        data = os.read(stream.fileno(), 8192)
                        if not data:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        buffer = output if key.data == "output" else errors
                        limit = 65536 if key.data == "output" else 4096
                        if len(buffer) + len(data) > limit:
                            raise ValueError("guest_output_limit")
                        buffer.extend(data)
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            if code != 0:
                raise CommandFailure(argv, code, errors)
            return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


class GuestTransport:
    def __init__(self, inventory, timeout=480):
        if set(inventory) != set(VM_IDS):
            raise ValueError("exact_fleet_inventory_required")
        self.inventory = inventory
        self.timeout = timeout
        for target in inventory.values():
            if set(target) != {"port", "identity_file", "known_hosts"}:
                raise ValueError("invalid_transport_inventory")
            if type(target["port"]) is not int or not 1024 <= target["port"] <= 65535:
                raise ValueError("invalid_control_port")
            for key in ("identity_file", "known_hosts"):
                path = Path(target[key])
                if not path.is_file() or path.is_symlink():
                    raise ValueError("missing_pinned_guest_credentials")

    def argv(self, vm_id):
        if vm_id not in VM_IDS:
            raise ValueError("unknown_target")
        target = self.inventory[vm_id]
        return ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-o", "BatchMode=yes",
                "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "UserKnownHostsFile=" + target["known_hosts"],
                "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ForwardAgent=no",
                "-o", "ClearAllForwardings=yes", "-o", "ConnectTimeout=5",
                "-i", target["identity_file"], "-p", str(target["port"]),
                "lab@127.0.0.1"]

    def request(self, vm_id, action, case=None):
        if action not in ("health", "solve", "containment"):
            raise ValueError("unknown_guest_action")
        request = {"action": action, "job_id": uuid.uuid4().hex}
        if case is not None:
            request["case"] = case
        raw = bounded_process(self.argv(vm_id) + ["lab-helper"], json.dumps(request).encode(), self.timeout)
        return bounded_json(raw, max_bytes=65536)

    def tunnel_argv(self, relay_port):
        if type(relay_port) is not int or not 1024 <= relay_port <= 65535:
            raise ValueError("invalid_relay_port")
        command = self.argv("controller")
        # Only the trusted host opens this fixed reverse relay. Guest SSH policy must
        # allow exactly PermitListen 127.0.0.1:18081 and deny all local forwarding.
        position = command.index("ClearAllForwardings=yes")
        command[position] = "ClearAllForwardings=no"
        return command[:-1] + ["-N", "-o", "ExitOnForwardFailure=yes", "-R",
                               f"127.0.0.1:18081:127.0.0.1:{relay_port}", command[-1]]
