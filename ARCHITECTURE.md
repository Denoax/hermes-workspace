# Architecture and boundaries

The current conversational path is documented in [LOCAL_CHAT](docs/LOCAL_CHAT.md).
Its unprivileged worker receives a root-attested connected socket and no model
tools. Durable ordered events, an atomic history cursor and explicit run ownership
support streaming/reload/cancel. Candidate release waits for verified normal
recovery. The original guest-execution architecture below remains separately gated.

The trusted host supervisor is small, deterministic and outside agent control.
It is independent of whether either model is willing to obey instructions.

| Component | Role and permitted access |
| --- | --- |
| Host supervisor | Fixed VM inventory/lifecycle, leases, quotas, case dispatch, evidence and independent scoring. Never executes model-supplied host shell. |
| Local model service | One pinned model at a time, narrowly confined non-root process with GPU access only as required; local inference endpoint. No server-side tools, agents or media-file access. |
| Inference relay | Authenticated, bounded text-only requests to the selected local model; no arbitrary URLs, admin endpoints, tools or cloud fallback. |
| Controller VM | Fresh Hermes lab configuration/state and guest workspace. Produces task requests/candidates; no host credentials or unrestricted network access. |
| Worker A VM | Disposable execution/inspection of provided owned task artifacts under guest limits. |
| Worker B VM | Separate worker for recovery tests, or reset into an independent clean validation instance. Never trusts another worker's claimed success. |

Default proposal: three small guests, one active model job at a time, one model
loaded at a time. Start around 3 GiB controller + 1.5 GiB per worker, subject to
actual memory/CPU checks. No GPU passthrough. The host model service handles
inference; guests exercise CPU tasks. Increase workload only from measured headroom.

## Networking

Prefer supported unprivileged QEMU/KVM with a dedicated restricted host UID, an
updated guest/host runtime, minimal virtual devices and per-VM disposable disks.
QEMU user-mode `restrict=on` blocks guest-originated host/outside IP connectivity,
but explicit forwarding remains an exception. Codex must verify this on the
installed version for both address families rather than assume a launch flag
is a complete proof. Host firewall state from the prior task must stay intact.

Use host-initiated authenticated control connections through private UNIX socket
forwarding if supported, otherwise explicitly loopback-bound forwarding with
unique reserved ports. No LAN/WAN binding, TAP/bridge to the physical LAN, default
NAT network, arbitrary guestfwd commands, guest-visible host directories or extra
NICs. Each guest has its own user-mode network. The fleet coordinates through
the trusted broker, not an uncontrolled shared LAN.

The inference channel is an explicit bounded exception: use a host-initiated
encrypted tunnel or equally constrained channel exposing only the authenticated
text-only inference relay inside the controller. It must not provide a generic
proxy, SSH agent, reverse SOCKS, filesystem or arbitrary host TCP access. The
model API's admin/load/slot/tool/media routes are not reachable from the guest.

Guests may not reach the router, LAN, host services, public destinations or cloud
metadata. Tests must prove an allowed control/inference path works and forbidden
paths are denied; a missing guest NIC or broken SSH is not isolation success.
Use owned loopback/controlled canaries and recorded host-boundary observations
instead of sending attack or scan traffic to third parties.

## Host process confinement

Run QEMU as a restricted host account without sudo or broad libvirt/Docker
authority. Restrict its filesystem view to that VM's disk and required runtime
files; protect personal home/config/credentials. Use supported systemd/cgroup,
namespace/LSM and QEMU sandbox controls with validation. Running an emulator as
the desktop user is not the desired containment for hostile guest behavior.
Configure per-VM CPU, RAM, process, disk/IO and lifecycle limits. Keep host reserve
for the desktop, current projects and model. No swap storm, indefinite disk
growth, priority starvation or silent bypass when /dev/kvm is unavailable.

A hypervisor can have vulnerabilities. This architecture reduces reachable
resources and limits damage; it does not establish immunity to VM escape.
Use benign generated fixtures in this first phase, not downloaded live malware.

## Authorization and watchdog

Model/controller requests use a fixed schema: run ID, approved VM ID, case ID,
action, unique job ID and expiring run token. Optional candidate content is
bounded and transferred as data into a fixed guest workspace. No caller-selected
host paths, executable names, process IDs, hypervisor args or shell fragments.
Reject unknown fields, unknown targets/actions, duplicates, malformed data,
expired/revoked authorization and exhausted quotas. Log denials without secrets.

Controller health and absolute run/job expiry are separate checks. Use host
monotonic time and an independent watchdog/system manager, not guest clocks or
an LLM's promise to stop. A running model request must not stall expiry. A live
heartbeat cannot extend the absolute run deadline. Losing the controller closes
dispatch, revokes relay access and safely pauses/stops only this run's guests.

Track exact VM UUIDs/process identities, owned paths and sockets. Never stop VMs
by broad process-name matching or delete a directory suggested by a model. Keep
automatic cleanup limited to disposable overlays/artifacts listed in the run
manifest, after evidence flush and path/identity checks. Preserve reports and
reusable base images. Stop/cleanup must be idempotent, including after crashes.

The packaged `starter/control_policy.py` is a tested reference schema/lease gate,
not a complete watchdog, VM monitor or security boundary. Wire real transport,
process controls and persistent recovery around it and test them separately.


## Workspace continuation

The unprivileged authenticated loopback UI owns the user project/session catalog and inert editable copies. It calls only strict versioned job/read/cancel operations through the native operator socket. Root owns job admission, committed model pins, FIFO execution, outside pidfd ownership, absolute leases and cleanup; the UI catalog mirrors that ledger for reconnect/export. Acting Hermes and file tools run in disposable worker_a, code/compiler children run as separate guest UID 1001, and a fresh independent worker_b receives only exports and outside-generated inputs. Original repositories are outside those guests. Hash-bound user review is the only apply path.

No-work broker availability after normal restoration is intentional for durable history/status. Starting that broker or opening the app starts no VM/model/window. Immutable model/backend files are byte-verified during no-GPU qualification and checked for drift at admission. PC Bunker owner/table/hooks are pinned; a parent-fenced native nft observer invalidates cached readiness. Full registered removal retires live hooks before referenced code, then thin namespaces and exact created lab identities, retaining original/copy/recovery/evidence/catalog data. See workspace/README.md and native/workspace_recovery.py.
