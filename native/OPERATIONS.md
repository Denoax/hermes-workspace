# Native operations and recovery

These helpers are deterministic root-owned setup/supervision code, not root
agents. Enter credentials only in native protected authentication. All normal
Hermes files, profiles, defaults and router authority are preserved.

Protected setup helpers live under `/usr/local/lib/mani-vmlab-setup`; private
records are `/var/lib/mani-vmlab-setup`. Lab-only data lives under
`/home/mani-vmlab-data` (root 0700). Public signed pacman downloads use the
separate `/home/mani-vmlab-package-downloads` cache with alpm traversal permission.

## Stop and remove the owned runtime

First close any active inference window and verify the original normal server's
health, alias and 65,536 context before removing runtime code:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/inference_window.py close
```

Then use `labctl stop` and `labctl cleanup` for each exact recorded run ID.
Verify `manibot-llama.service` is loaded and active, its model endpoint is healthy,
and `/run/user/1000/systemd/user.control/manibot-llama.service` no longer exists.
The window removes only its root-recorded mask inode; never delete a replacement
override or a mask installed by another actor.
For a native recovery console, inspect the root-owned rollback dry run:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/rollback_runtime.py
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/rollback_runtime.py --apply
```

The rollback checks recorded inodes/hashes, stops only the lab supervisor/runs,
removes only registered installation files, and retires the lab account only if
it was created here, still matches and has no remaining processes. It retains
base images, all package backups and run evidence. A changed/unregistered file
is preserved and reported. Native rollback application itself is not yet tested.
Previous runtime source/config/unit registers are retained under
`/home/mani-vmlab-data/runtime-versions`. Partial updates require review of those
specific records; do not recursively delete the data directory.

## Package recovery

All 2,844 original cache files (4,929,430,724 bytes) were copied and independently
hash checked before their registered originals were unlinked. Every old version
of the 98 upgraded packages has a verified detached package signature. A private
package database/config backup is `maintenance-recovery/package-db.tar` under
the lab data directory; its SHA-256 is
`4b880694eeb60709259e4dccddfa47ba22330c7cf7e6c9204e53006dc0cc5f65`.
Preparation and installation records identify every package/version and archive.

A coherent OS downgrade needs the whole affected package set, the matching old
Quickshell build, and native-console dependency review. Do not selectively
roll back NVIDIA or Qt, restore only the DB over newer files, use --nodeps, or
force a reboot. Generate/review pacman's downgrade plan against the root-owned
archive register before applying; full OS rollback has not been exercised.
NVIDIA installation regenerated the existing kernel's UKI through package hooks.
The user's native reboot completed successfully. Booting old recovery artifacts
or testing the physical recovery console remains unverified.

To restore the original cache location after sufficient root space is available:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/setup.py cache-restore
```

This retains backup copies and checks bytes; recreated files have new inodes and
0600 mode. It does not restore original metadata. Native cache restoration has
not been exercised. No journals, Flatpak/container data or personal files were
pruned/migrated. The package helper never handled credentials in chat/tools.

## Evidence and remaining work

`results/continuation` separates actual VM probes, package changes, artifact
provenance and offline fixtures. The no-agent watcher uses real pidfds outside
workload cgroups, plus system-manager BindsTo/WatchdogSec and absolute runtime
limits. Protected `watchdog_probe.py all` creates fresh fleets and cleans them.
Do not expose root setup/test helpers or the operator socket to a guest/model.

The normal server remains at its original 65,536 context; measured lab context is
8,192. A distinct chosen inference window is required before pausing only
`manibot-llama.service`. Dedicated backend cancellation/restoration, real guest main-model calls, paired
artifact loading and effective-tokenizer equality have actual receipts. Host
firewall policy was observed; physical LAN/WAN, auxiliary/tool workers and fresh
candidate-code validation remain unverified. Matrix execution is gated by all six
smoke answers passing; a failed score is preserved, not rescued by a larger cap.

## Model preparation and window recovery

Protected model storage adds copied normal/candidate weights, a pinned b9980
runtime, a thin backend root, and model account UID/GID 958. These copies preserve
the normal original. The model account has no personal home or Docker/wheel groups.
The window unit is lab-only and is not enabled at boot. Its independent ExecStopPost
restores only the previously active normal model service after stopping the lab.
Actual owner-crash and natural-expiry recovery restored health and unchanged
configuration. A separate live probe observed backend processing and cgroup CPU
activity before proving backend process exit; it did not observe decoding tokens.

The original runtime rollback helper covers its initial VM installation/account.
It does not retire the later model account or remove the later window unit/model
copies. Before applying it, stop the lab backend, close and verify the inference
window, and retire the window unit only after comparing its exact bytes with the
reviewed `window.unit_text()` and retained unit backup. An installed window unit
must not be left pointing at runtime code that has been removed.
Keep the protected inference preparation
register, account IDs and exact unit content for native-console review; preserve
changed/unregistered files and all recovery archives. Full OS downgrade, cache
restoration and native runtime rollback application remain unexercised.

Later additions are recorded in `/var/lib/mani-vmlab-setup/inference-preparation.json`
and `backend-artifacts.lock.json`: model UID/GID 958, copied model files,
`/home/mani-vmlab-data/backend-b9980`, thin backend root and control directory,
and the fixed lab window/backend units. Preserve copied weights/runtime by default.
Retiring the account requires its recorded identity, no remaining processes, and
review of retained file ownership; never remove the original normal weights or
the packaged qemu account. Source/unit backups are under `runtime-versions`.
These later removal steps are manual review steps, not a tested one-command uninstall.
