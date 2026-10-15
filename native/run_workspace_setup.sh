#!/bin/sh
# Reviewed lab-only setup and no-GPU qualification; native credentials only.
set -eu
task_workspace_helper=/home/mani/mani-hermes-vm-lab-43x3qx7c/MANI_HERMES_VM_LAB_Codex_Handoff_v1/native/workspace_setup.py
task_workspace_digest=$(/usr/bin/sha256sum "$task_workspace_helper")
task_workspace_digest=${task_workspace_digest%% *}
if [ "$task_workspace_digest" != "6da99bfeddd51409e669f3312e5ce9b41f63182552c4afcee7a1afdb0e8600af" ]; then
    printf '%s\n' 'Prepared helper changed; stop and review the new transaction.' >&2
    exit 1
fi
sudo /usr/bin/install -o root -g root -m 0644 "$task_workspace_helper" /usr/local/lib/mani-vmlab-setup/workspace_setup.py
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/workspace_setup.py apply
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/workspace_acceptance.py qualify
