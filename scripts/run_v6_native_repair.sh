#!/bin/sh
# Native operator entry point. Read/apply $reference-led-design for continuation.
# No credentials are accepted by this script; sudo uses the native terminal.
set -eu

if [ "$(/usr/bin/id -u)" != 1000 ]; then
    echo 'Run this as the normal workstation operator, without sudo.' >&2
    exit 2
fi

cd /home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1
/usr/bin/sha256sum --check <<'HASHES'
3c80a7b77e9964d8d799baab7b7cb96c19cdf65ee2c7f5a417b121a69cf70d43  native/production_x11_setup.py
1be045ad0943e6ddc022eb0da0194677e747485ec27e96d06302c1e4e8c5dc30  native/backend_writer_setup.py
e52e8ce5c600361764e41b790f1d8a611d1fdce17ee838f013bf6627b6931116  native/backend.py
HASHES

echo 'Installing the frozen native repair helpers. Keep Hermes idle.'
/usr/bin/sudo /usr/bin/install -o root -g root -m 0644 native/production_x11_setup.py /usr/local/lib/mani-vmlab-setup/production_x11_setup.py
/usr/bin/sudo /usr/bin/install -o root -g root -m 0644 native/backend_writer_setup.py /usr/local/lib/mani-vmlab-setup/backend_writer_setup.py

# Check the protected copies too: a checkout file could change after the first
# hash check. Root-owned parents keep these verified copies stable for execution.
/usr/bin/sha256sum --check <<'INSTALLED_HASHES'
3c80a7b77e9964d8d799baab7b7cb96c19cdf65ee2c7f5a417b121a69cf70d43  /usr/local/lib/mani-vmlab-setup/production_x11_setup.py
1be045ad0943e6ddc022eb0da0194677e747485ec27e96d06302c1e4e8c5dc30  /usr/local/lib/mani-vmlab-setup/backend_writer_setup.py
INSTALLED_HASHES

echo '1/3: reconcile only the known backend unit mode; keep its approved bytes.'
/usr/bin/sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/production_x11_setup.py reconcile-backend-mode
echo '2/3: install the registered writer correction and refresh the idle broker.'
/usr/bin/sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/backend_writer_setup.py apply
echo '3/3: add the read-only X11 directory bind and restart only the app runtime.'
/usr/bin/sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/production_x11_setup.py apply
echo 'Repair sequence complete. No inference was requested.'
