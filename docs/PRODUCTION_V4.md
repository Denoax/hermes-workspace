# Production admission and permission boundaries

Read/apply `$reference-led-design` for visual continuation. Reuse the exact
published references and owned portfolio buddy; no generated media, substitute
references or invented human approval. Source and rendered evidence are separate.

## Why the pin failed

The v3 desktop user service enabled `PrivateTmp=yes`. In systemd's user manager,
that also requires a user namespace mapping only the operator UID. The real root
socket and its root peer appeared as unmapped UID 65534. Interactive and isolated
acceptance processes used a different context, so they could succeed while the
actual authenticated production route reported missing protected admission.
Explicit `PrivateUsers=no` in that user unit did not remove the implicit mapping.

The corrected system manager creates the private temporary/mount namespace and
then runs the data service as UID/GID 1000, with no capabilities and
`NoNewPrivileges=yes`. The original root identity remains visible. No socket mode,
root-peer check, authorization, firewall or normal-model setting is relaxed.

- `hermes-workspace-runtime.socket`: system socket, **127.0.0.1:18791 only**.
- `hermes-workspace-runtime.service`: normal-user app, inherited fixed listener.
- `hermes-workspace.service`: existing user lifecycle/pin entry, now a thin client.

Opening the unchanged pin triggers the socket through its safe health check.
Restarting the user unit stops only the verified, same-UID app PID using a pidfd;
the next health request activates its replacement. Model leases remain outside
the app process. Display-session coordinates are refreshed through a whitelist
only when an explicitly requested native GUI operation needs them.

## Permissions are separate from model readiness

Existing conversations start in **Chat only**. Explicit attachments remain inert
context. **Ask before actions** offers normalized, expiring approval cards.
**Workspace agent** permits selected copy reads/writes and qualified guest tasks;
Wikipedia and microphone consent remain separate settings. Granular differences
are shown as Custom. Changing models does not widen a policy.

Policies, grants and actions live in SQLite, bound to the local UID, conversation,
selected project and policy version. Approvals additionally bind the normalized
arguments, originating run and file bases. Allow once is consumed durably before
effects; narrow session grants expire. Reconnect returns the same receipt. Denial
survives model retries, and revocation invalidates outstanding tickets.

Descriptor-anchored `Files` enforces paths, mount/symlink boundaries and stale
bases at dispatch. Search uses the fixed Wikipedia provider. Native guest tasks
need the existing current qualification/window and retain their fixed schema;
unavailable execution has no host-shell fallback. The current Python oracle
clamps JSON integer arrays to 0–100; C++ squares input integers. These are fixed
supported validation contracts, not arbitrary Python/C++ correctness claims.
Chat and diagnostic guest results require manual review. Applying a reviewed diff to an
original host file always requires separate one-use approval. Publication is
outside the model's action schema.

Model proposals use four flat function schemas (`workspace_read`,
`workspace_write`, `search_wikipedia`, `guest_submit`), translated into the same
strict normalized actions: one action per turn, bounded fragments/results and a
finite run budget. Real production calls with the initial union-only parameter
schema returned empty arguments and were rejected. The flat schemas resolved
that observed failure without granting authority. The older tagged adapter is
retained for compatibility; it cannot request original-file application. Prose cannot change
policy or approve anything. Text compute is released before action dispatch.
Pending actions remain in the approval UI; completed observations can inform a
subsequent turn. This is not an unlimited autonomous command loop.

Microphone capture checks server-held app consent before requesting browser
permission. Explicitly uploaded audio can be transcribed without granting access
to a physical microphone. Browser/device permission is an additional boundary.

## Prepare, verify and recover

`scripts/prepare_production_setup.py PRIVATE_DIRECTORY` freezes the bounded
no-GPU installer. Install/run it only at its fixed root-owned path through native
authentication. It checks the four normal configuration hashes, source pins,
existing recovery fingerprints and a disposable nonroot namespace/root-peer proof
before changing the UI launch context. It records root-private rollback data and
updates only this app's fixed units and recovery registrations.

`production_setup.py rollback` restores only the recorded installation when all
fingerprints still match. It never replaces the catalog or normal-model files.
Do not rerun the historical v3 reset. Preserve newer conversations and edits.

Production acceptance uses `scripts/production_pin.py`: the actual launcher,
dedicated profile, catalog and port 18791. Its private CDP instrumentation pauses
only the launcher's polling loop and always resumes it. It supplies no replacement
authentication, model replies, catalog or test server. Other-port tests are
supporting evidence only. Reboot, physical devices/listening and human continuous
motion approval must be labelled separately when unavailable.


## Reboot prerequisites and failure handling

The unchanged desktop pin now recreates only the operator-owned temporary
`/run/user/1000/systemd/user.control` directory when absent. Descriptor checks
reject symlinks, a foreign owner or writable parent/child. This directory is
required by the protected window unit's existing `ReadWritePaths`; after a reboot
its absence otherwise causes `226/NAMESPACE`. No mount restriction, root-peer
check or window admission is weakened. The launcher also checks its actual
compositor surface after sizing so that a restored off-screen position cannot
hide the rail.

All authenticated frontend operations wait for CSRF bootstrap. A service restart
may rotate CSRF: only the server's pre-dispatch authentication refusal is retried
once with the same operation body. Permission denials and ambiguous transport
errors are not replayed. A failed turn with no public answer has an explicit
same-ID retry; partial replies remain intact and require a follow-up.

Current model readiness is distinct from installed-model inventory. Candidate
Send requires current native artifact verification, and resource ownership keeps
new turns out while recovery or guest work owns the GPU. Listing models hashes
or loads no weights. Full verification remains an explicit protected operation.

The optional fixed `diagnose_guest_boot.py` helper records only sanitized health
reply/error categories for an unchanged-budget, no-agent boot. It never grants
qualification, modifies the runtime policy or starts inference. Its standalone
root-owned diagnostic file has no service and is outside the production repair
transaction; remove only that exact file after verifying its recorded SHA when
retiring the diagnostic. Keep its sanitized receipt as adverse evidence.

Cancel and Revoke remain responsive during provider/native I/O. Before publishing
returned search context or committing effects the dispatcher rechecks the policy,
run, expiry and original file base. A started remote request cannot be undone;
a native guest admission acknowledged after revocation is explicitly cancelled.
Browser microphone permission resolving after Cancel immediately releases the
late tracks; device loss retires capture and its meter. Deterministic device
fixtures do not establish physical microphone or listening quality.

## Rollback limits

Keep the private source snapshot and consistent catalog backup from before v4.
Native rollback checks the recorded exact file identities and refuses drift; it
must run through native authentication. Restore only the reviewed source files
and rebuild the UI when reverting source. Keep the current catalog, including
all newer conversations. Restore an old catalog only after stopping this app and
making a new consistent backup, and only when explicitly choosing to discard
newer records. No delete-all reset is part of v4.

The native installer journals completed writes and uses atomic file replacement.
Its fixtures cover ordinary failure rollback; process death between replacement
and journal persistence has not been established as crash-atomic recovery.
Reinstalling an identical native helper can change its inode and cause the
recovery register to refuse drift. Inspect that precise refusal; do not overwrite
the register or force a rollback. The installed transaction and private original
bytes remain the recovery authority.
