# Recovery and rollback

Read/apply $reference-led-design for any later visual changes, preserve accepted source and measurements, and keep credentials in the native terminal. These are operator actions; neither the UI nor a model can execute them.

Closing the inference window is the first recovery action. In a native terminal:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/inference_window.py close
```

The guard stops only the owned lab supervisor/fleet/backend, removes its exact recorded runtime mask and recovers the original normal service. It verifies health, alias `qwen3.6-35b-a3b-q4`, context 65536 and the configuration hashes. A restored no-work native broker is intentional for history/status; it starts no model/VM/window. Independent deadlines and system-manager bindings still handle owner death. Do not open another window to conceal a failed result or expired approval.

For a complete registered removal, first inspect its concrete plan:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/workspace_recovery.py plan
```

Only when intentionally removing the lab, run:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/workspace_recovery.py remove
```

The plan refuses changed file identities/hashes, symlink ancestors, altered private backups, unknown runtime contents and unregistered identities. Removal verifies normal recovery, stops the user UI/owned dedicated browser and backend/supervisor, retires window/model/service hooks before their code, reloads managers, restores the unchanged original Steam pin/router wrapper, removes exact thin namespaces and retires only created `mani-vmlab-model` UID 958 and `mani-vmlab-vm` UID 959. Packaged QEMU/RDMA identities are excluded.

Retained deliberately: original and copied weights, backend binaries, base images, package/database/cache recovery, run/job receipts, private catalog/browser data, source/version backups and fixed setup/recovery helpers. Removal does not delete those directories recursively or wipe evidence. The source router repository is retained; restoring its installed wrapper does not silently reset the source checkout. Review its two-file patch before reverting source changes.

The native update journal is `/var/lib/mani-vmlab-setup/workspace-update.json`; its `backup` identifies the protected pre-update checkpoint under `/home/mani-vmlab-data/workspace-recovery/before-*`. It preserves the original runtime source tree, lab configuration, supervisor unit, installer/register/lock/source pack and prior runtime ISO. The prior source updater also retains its registered version under `/home/mani-vmlab-data/runtime-versions`. Do not export these private checkpoints.

A failed partial transaction is not success. Stop inference first, retain the error/receipts, and resume only the same frozen input after diagnosis. `workspace_setup.py apply` permits a matching journaled continuation and verifies the committed pack. Changed inputs or later native work are preserved and require a freshly reviewed transaction; do not overwrite the register merely to make it pass. Exact version rollback should restore the checkpoint's source, configuration, unit, helpers/pack/lock/ISO and recompute its registered identities with that checkpoint's installer before restarting. This manual version rollback is distinct from registered complete removal and is not advertised as an exercised production operation.

The full removal/reinstall acceptance uses actual disposable guest systemd managers, exact created fixture accounts and owned stand-in units. That proves ordering and registration against real managers. It does not certify production uninstall, physical recovery console/rescue, LAN/WAN ingress or subjective device/visual approval. Actual acceptance status belongs in the final measured report.
