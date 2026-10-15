#!/usr/bin/python3
"""Fixed protected offline guest artifact installation; no agent or model runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

SELF = Path('/usr/local/lib/mani-vmlab-setup/prepare_guest.py')
SOURCE = Path('/home/mani/mani-hermes-vm-lab-43x3qx7c/private-artifacts/guest-hermes/runtime.iso')
TARGET = Path('/home/mani-vmlab-data/artifacts/runtime.iso')
ISO_SHA = 'b9c768272dbcf6ba53509297ed497a35f928341ff2a3e0c64b4a255c5dd922bb'
ZIP_SHA = 'df3b9b6bf0ab4f2fad513b034db20cd3b7ba8f0623b8e0a995572a7b9b7d76a7'
REVISION = '63279301bcbdc185c1b07b98a9312eb0c862f26d'
CONFIG = Path('/etc/mani-vmlab/config.json')


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('fixed_protected_guest_preparation_only')
    sys.path.insert(0, str(SELF.parent))
    from install_runtime import trusted, checkpoint, sha256
    for path in (SELF, SELF.parent, SELF.with_name('install_runtime.py'), CONFIG):
        trusted(path)
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('apply', 'status'))
    operation = parser.parse_args().operation
    if operation == 'apply':
        subprocess.run(['/usr/bin/systemctl', 'stop', 'mani-vmlab-supervisor.service'], check=True, timeout=30)
        # Updating the runtime already stopped/cleaned all registered fleets.
        runs = Path('/home/mani-vmlab-data/runs')
        if any(json.loads((d/'manifest.json').read_text())['status'] == 'active' for d in runs.iterdir() if d.is_dir()):
            raise RuntimeError('stop_owned_fleet_before_guest_artifact_change')
        TARGET.parent.mkdir(mode=0o700, exist_ok=True)
        trusted(TARGET.parent, directory=True)
        if TARGET.exists():
            trusted(TARGET)
            if sha256(TARGET) != ISO_SHA:
                raise RuntimeError('preserve_changed_guest_artifact')
        else:
            descriptor = os.open(SOURCE, os.O_RDONLY|os.O_NOFOLLOW)
            temporary = TARGET.with_suffix('.new')
            try:
                with os.fdopen(descriptor, 'rb') as source, temporary.open('xb') as output:
                    checksum = hashlib.sha256()
                    while chunk := source.read(4*1024*1024):
                        checksum.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if checksum.hexdigest() != ISO_SHA:
                    temporary.unlink()
                    raise RuntimeError('frozen_guest_artifact_digest_mismatch')
                os.chown(temporary, 0, pwd.getpwnam('mani-vmlab-vm').pw_gid)
                temporary.chmod(0o440)
                temporary.replace(TARGET)
            except BaseException:
                raise
        mountpoint = Path('/home/mani-vmlab-data/runtime-root/vm/artifacts')
        if not mountpoint.exists():
            mountpoint.touch(mode=0o600)
        trusted(mountpoint)
        config = json.loads(CONFIG.read_text())
        config.update(runtime_iso_sha256=ISO_SHA, runtime_zip_sha256=ZIP_SHA, Hermes_revision=REVISION)
        CONFIG.write_text(json.dumps(config))
        register = json.loads(SELF.with_name('runtime-installed.json').read_text())
        checkpoint(register)
        subprocess.run(['/usr/bin/systemctl', 'start', 'mani-vmlab-supervisor.service'], check=True, timeout=30)
    print(json.dumps({'status': 'ok', 'installed': TARGET.is_file() and sha256(TARGET) == ISO_SHA,
                      'runtime_iso_sha256': ISO_SHA, 'host_agent_executed': False,
                      'normal_services_changed': False}))


if __name__ == '__main__':
    main()
