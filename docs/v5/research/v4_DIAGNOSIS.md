# Production send failure

## Confirmed from the new screenshot and v3 source

The screenshot shows two user messages, no assistant answer and `protected_text_admission_not_installed`. The candidate is described as installed/unloaded. A model file being present is not proof that protected admission is available.

In `lab/native_client.py`, `NativeClient.text_connection()` raises that exact error before a model connection if `NativeClient.available()` is false. The readiness predicate requires:
- `/run/mani-vmlab/control.sock` to exist and be a Unix socket owned by UID 0;
- its parent to be owned by UID 0 and not group- or world-writable.

A missing path returns false. Other filesystem access errors may propagate differently. This error does not by itself prove the supervisor was never installed. The actual PC must establish which condition failed.

The text channel separately requires a root peer via SO_PEERCRED, fixed admission schema and a connected descriptor passed by SCM_RIGHTS. Preserve these boundaries.

`workspace/server.py` exposes `capabilities.read.text_admission` as a boolean; the frontend fetches capabilities but still allows the observed failed-send experience. Model inventory checks files and model identity, not production admission readiness. Queuing a chat and displaying the raw exception is not adequate readiness/error handling.

The socket unit in `native/local_chat_setup.py` listens at the same path, root-owned, mode 0660, directory 0755, enabled under sockets.target, with RemoveOnStop=yes. Setup adds RuntimeDirectoryPreserve=yes to the supervisor service. The supervisor accepts systemd's inherited fd 3 and only unlinks a self-bound socket, not an activated one. Do not invent an unconditional unlink bug.

`native/window.py` restores normal Qwen and then restarts the supervisor when the root configuration enables workspace API. Service restart, runtime directory lifetime, socket activation, setup drift and cleanup ordering need actual host evidence.

## Establish the actual native cause

Before changing anything, record:
1. The process serving 18791, its exact executable/source/UI hashes and user-service identity. Do not dump auth tokens or the full environment.
2. Socket and parent lstat facts as seen by that actual user-service context, not only an interactive shell.
3. Socket/service ActiveState, SubState, UnitFileState, Listen, RuntimeDirectory, RuntimeDirectoryPreserve, TriggeredBy and Triggers; installed unit paths and expected owned setup digests.
4. Whether the current native updater installed the reviewed socket support, and whether the enabled socket survives normal recovery/test cleanup. Use bounded journal excerpts privately and sanitize public evidence.
5. Whether the app's actual process namespace, source or catalog differs from isolated acceptance. Do not assume a namespace issue just because one is possible.

The bundled script gathers an initial subset without connecting or modifying services. It is not proof of current PC state until run there.

## Repair and user-facing behavior

Use the existing frozen native installer/updater and ledger; prepare any needed correction in source first, review its bounded privileged changes, then authenticate locally. Root metadata checks, peer checks and watchdog ownership stay intact. Never use chmod 777, an always-true readiness result, direct model-port bypass or web-initiated sudo.

Provide a typed readiness result that separates:
- installed/linked model and supported capabilities;
- trusted control channel present;
- actual admission/lease availability;
- cold loading, recovery, generation, cancellation and error.

Keep expensive model loading out of routine readiness probes. Map the error to clear text such as “Local model connection needs repair” with useful details and an honest recovery action. A Recovery button may retry a safe supported probe; it cannot silently elevate or claim a repair without one.

On a failed send, preserve the draft/attachments and conversation. Mark the failed turn and offer retry. Use a stable submission/turn identity so double clicks, reconnects or retries cannot create duplicate active generations or extra user bubbles. Validate readiness at the server too; the UI check alone is not enforcement. Show real model loading activity and elapsed time for the slow candidate; do not present a silent spinner as a reply.

## Acceptance gap that must close

The earlier real model trials used isolated acceptance catalogs on ports 18793/18794. They are legitimate evidence about those trials, but the user's production pin at 18791 is failing. Record the fix after full test cleanup, normal-model restoration, a fresh pin launch, idle and socket activation. Preserve the failure evidence and distinguish the observed failed condition from any unconfirmed hypotheses.
