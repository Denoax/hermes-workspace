#!/bin/sh
# Complete only the exact interrupted X11 transaction; no app restart or inference.
set -eu
umask 077

lab_root=/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1
cd "$lab_root"
printf '%s\n' '4fa0701f5a2c50eddc66d526d19571c636c891175b8a9f02712346674fe46a3f  native/production_x11_finalize.py' | /usr/bin/sha256sum -c -
printf '%s\n' 'Installing the reviewed completion helper; protected phase and runtime checks precede completion.'
sudo /usr/bin/install -o root -g root -m 0644 "$lab_root/native/production_x11_finalize.py" /usr/local/lib/mani-vmlab-setup/production_x11_finalize.py
printf '%s\n' '4fa0701f5a2c50eddc66d526d19571c636c891175b8a9f02712346674fe46a3f  /usr/local/lib/mani-vmlab-setup/production_x11_finalize.py' | sudo /usr/bin/sha256sum -c -
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/production_x11_finalize.py complete
