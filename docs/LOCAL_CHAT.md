# Local chat operation and recovery

Read/apply `$reference-led-design` for visual continuation. Preserve the accepted identity and sounds. Use inspected sources and original code; no generated media, fake activity or approval claims.

## Ownership

`workspace/server.py` owns authentication and the loopback API. `Conversations` owns durable runs/events/history and folder invariants. `Chat` owns one bounded FIFO and cancellation. The view receives atomic snapshots and ordered NDJSON; the snapshot cursor prevents duplicating already persisted partial text on reload. Numbered citations resolve only against that turn’s actual sources, leave code/existing links literal and preserve the original model text.

`Inventory` accepts only explicit links with a verified full hash and unchanged file identity. Listing neither scans disks nor loads models. Normal identity also checks four configuration hashes, systemd MainPID, exact model/runner argv, runner hash, alias and context. Candidate bytes are independently checked in the protected native store.

The supervisor admits only a fixed job ID and arm. SCM_RIGHTS transfers a connected backend socket; no prompt, model output, arbitrary URL/path or tool command enters the root protocol. Heartbeat loss, owner pidfd death and a 300-second request deadline revoke it. Candidate inference also uses the 30-minute guard. Cleanup sends its acknowledgement before daemon shutdown. The guard has no circular stop-order dependency and serializes recovery. The worker remains `restoring` until normal identity is verified again. Text chat has no executable tools; existing guest tools keep their separate gates.

## Limits

- Four waiting requests, one execution owner; no overlap within a conversation.
- Messages: 12,000 UTF-8 bytes. Replies: 1,024 tokens / 32 KiB persisted text.
- Context: actual template/tokenizer measurement with output reserve; oversized history fails explicitly.
- Uploads: eight user files per turn, 8 MiB each, 32 KiB text and a private storage quota. Type/magic, links and traversal are checked; media is authenticated.
- Images preview only. No vision comprehension is claimed for these local text models.
- Voice: explicit capture, two-minute limit, local CPU English tiny Whisper. Permission/device/codec failures remain errors.
- Search: only an explicit Wikipedia query leaves the PC; fixed HTTPS provider, public DNS connection pinning, no redirects/arbitrary destinations.

Vulkan memory exhaustion can require pausing GPU workloads and restarting the existing runner after allocator failure. Do not change the normal flags to hide a failed test. Candidate loading is expensive because each reply restores normal Qwen. Its 8,192 context differs from normal's original 65,536; these are functional checks, not an equivalent-quality benchmark.

## Preparation and verification

Rebuild with the pinned lockfile, then restart only `hermes-workspace.service` after owned requests finish. Native preparation requires existing private workspace media/backups and the verified installed source-pack identity:

```sh
python3 scripts/prepare_local_chat_setup.py PRIVATE_STATE \
  --workspace-state EXISTING_PRIVATE_WORKSPACE_STATE \
  --previous-pack VERIFIED_INSTALLED_PACK_SHA256
```

The frozen helper is installed in its fixed root-owned location through native authentication. Its explicit `apply` operation backs up prior files, updates this lab, rechecks normal hashes/backend copies, rebinds the socket and updates the recovery ledger. It starts no inference and changes no host packages. Never publish private prepared inputs or treat the placeholders above as a portable installer.

`scripts/serve_chat_acceptance.py` runs this same app on fixed loopback 18793 or 18794 with a separate catalog and no substituted replies. Inference expires 30 minutes after its first captured Send, including restarts. The live, flow, media, native-pointer and lease probes label real inference separately from fixtures. An unattended overnight authorization does not imply human visual, physical microphone or listening approval.

## Rollback

Normal model/configuration files were not changed. Stop new requests and let the guard restore normal Qwen. Verify the original active service, alias, 65,536 context and four hashes. Native recovery if required:

```sh
sudo /usr/bin/python3 -I /usr/local/lib/mani-vmlab-setup/inference_window.py restore
```

The review includes the exact private backup locations and captured-ID reset receipt. Before any restore, stop `hermes-workspace.service`, preserve the current state and check for newer work. Restore only captured scope; do not overwrite later records. The reset backup was restore-tested in a disposable catalog. Production stays empty for delivery, so acceptance never restores it there.

A visual rollback should retain the native stop-order/socket/receipt fixes. Do not reinstall the earlier guard deadlock. Use registered `workspace_recovery.py plan` before native removal; drift checks intentionally preserve unrelated changes. Production uninstall was not applied. GitHub source rollback is an ordinary reviewed revert preserving newer commits, never a reset or force-push.
