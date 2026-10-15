# Implement the automated isolated lab

HANDOFF TYPE: Implementation and local verification with starter assets.
ASSET PACK REQUIRED: This complete handoff ZIP.

Mani authorizes an automated isolated VM fleet using Hermes and his normal
Qwen3.6-35B model plus a separate abliterated candidate to test local AI limits.
Preserve the normal setup and existing Codex/Hermes authority-aware routing.
Complete implementation and an actual bounded paired smoke when dependencies
allow. Do not stop with only architecture, or call fixture tests a model result.

Read/apply `$reference-led-design` or bundled snapshot. This is nonvisual:
original technical sources, reuse existing approved code and no generated media.
Read applicable AGENTS instructions and inspect the actual personal PC, existing
Hermes/router/backend, VM tooling and the completed hardening state. Do not use
settings from AAFC/Lethdome or change ISP/router infrastructure.

## A. Dependency and feasibility checks

Wait for the existing PC-hardening transaction to finish before changes to host
services/permissions/networking. Stage code, inspect docs and run offline tests
independently while waiting. Confirm the target PC and local recovery access.
Inspect CPU virtualization and /dev/kvm access, OS/QEMU/KVM versions, running
services, CPU/RAM/VRAM/storage, installed model metadata and Hermes revision.
Audit actual firewall protections after any setup change. Preserve ongoing work.

Create one new local project/worktree without overwriting unrelated files. Reuse
compatible router/protocol/validators where inspected contracts fit. Build fixed
host control interfaces instead of making Hermes a host administrator. Preserve
the existing default Hermes profile, gateways, memory, secrets and auth. Copy
only selected code/config values into a fresh guest lab installation; never clone
the user's complete Hermes home or .env. No pushes or deployment.

Native sudo authentication can be needed for reviewed package/user/service setup.
Do not collect credentials in chat. Prepare backups and exact removal/restoration
of new service/config/account changes. No broad sudo/libvirt/Docker privileges
for lab agents. No firmware, repartitioning, boot-key enrollment or forced reboot.

If hardware/space is insufficient, finish controller/schema/fixture work and
report the exact resource gap. Do not silently substitute containers/TCG as
equivalent isolation/performance or purchase/cloud-provision infrastructure.

## B. Trusted setup and VM lifecycle

Implement `labctl doctor`, `provision`, `smoke`, `run`, `status`, `stop`, `cleanup`
and `report`, with dry-run support for mutations. Provisioning is idempotent and
uses pinned updated official guest images/checksums/signatures and reviewed
dependencies. Separate trusted artifact preparation from agent execution. If
temporary provisioning network access is necessary, agents are absent/inactive,
no personal credentials are present, and the restrictive final NIC/config is
established and verified before execution. Do not leave a NAT network enabled.

Prefer the architecture's dedicated non-root QEMU/KVM setup. Confirm installed
support for restricted user networking and private/loopback control forwarding.
Verify containment beyond the flag: filesystem, IPC, device and process limits,
both network families, DNS, host/LAN/outside reachability, and permitted relay.
Avoid public VNC/SPICE/SSH/model endpoints, host filesystem sharing, agent
forwarding, extra guest NICs or GPU passthrough. Default resources are proposals
to adjust from measured headroom, not automatically reserved entitlements.

Use immutable base templates and per-run disposable overlays with unique UUIDs.
Record exact owned process IDs/start identities and artifact paths. Generate
ephemeral lab credentials with least privilege, pinned guest host keys and no
shared personal keys. Fixed guest helpers receive JSON/stdin; model output
never becomes a host shell command. Enforce guest timeout/resource caps at the
outside VM/service boundary. Cleanup touches only this run's registered state.

An independent supervisor watchdog and absolute runtime deadline must survive
Hermes/Codex failure. A missed controller heartbeat or expired lease revokes
dispatch and model access and safely pauses/stops only the owned fleet. Record
why a stop happened. Evidence collection must not delay the final hard timeout.
Implement reliable crash recovery and idempotent stop without `pkill qemu` or
recursive deletion of caller-selected paths. Test owner crash, stalled inference,
heartbeat loss, clock anomalies, replay, quota exhaustion and unauthorized VM IDs.

## C. Hermes and local-model connection

Install/reuse a pinned Hermes build INSIDE the controller VM. Use a fresh lab
home/profile with no imported keys, gateways, cron, plugins or persistent memory.
Select only required guest-local tools or the fixed broker tools. Local terminal
tools, if enabled, must execute in the guest, not the host. Default concurrent
delegation is one. Never expose hypervisor controls or host administrator tools.

Audit primary AND auxiliary requests (compression, titles, vision, approval,
delegation, background reviews and plugin providers). Route needed inference
exclusively through the constrained local relay; disable unused tasks and all
remote fallbacks/cloud credentials. Verify the actual config schema and effective
runtime; do not paste future-version YAML into an older Hermes install. Profiles
are configuration separation, not filesystem/network isolation.

The relay authenticates each run, checks lease/quota, caps input/output and request
duration, and talks only to the pinned local backend. It exposes no URL fetch,
model-load/admin/tool execution/media/file endpoints. Use text-only content and
explicit fixed tool contracts when needed. Preserve native tool-call semantics
and actual stop reasons in results. No hidden stronger-model routing to rescue
an arm. Never let the model judge/approve the supervisor's permission decisions.

Confirm the normal GGUF/backend and fetch a separate proven-compatible candidate
per MODEL_COMPARISON.md. The guest does not download or install weights. Keep the
model service isolated too: loading a community GGUF still exercises a host parser.
Prefer a narrow non-root lab service with required weight/GPU access and no
personal home/secrets. Verify backend output, JSON and tool-call behavior on both
arms before the paired tasks. Match execution settings and preserve the default.

Only one large model is loaded for lab work at once. If the normal server occupies
GPU memory, coordinate an idle window, save and restore its exact known service
state, or report that dependency. Do not kill active unrelated inference or
arbitrary listeners to acquire a port. Never overwrite/delete normal weights.

## D. Tasks, scoring and automation

Reuse the 12 owned fixtures and scorer as the initial reproducible matrix. They
test heartbeat/log reasoning, authorized scope, prompt injection, expiry,
configuration reasoning, code repair, simple disassembly interpretation,
duplicate recovery, evidence discipline, resource planning and arithmetic.
The fixtures are synthetic inputs; they are not captured real malware/incidents.
Keep answer keys and grading code outside all agent-accessible guests. Feed only
case prompt/assets into the workspace. Root-owned guest helpers/compiler paths
and fresh validation snapshots must not be editable by the solver.

For code candidates: compile/run ONLY in an isolated guest, never on the host.
Validate in a fresh independent guest with immutable reference inputs/known-good
behavior and host-owned evidence. Do not trust an agent-reported pass/exit status.
The toy C source is owned, provided for creating a binary/disassembly challenge;
the model-facing task initially uses a simple instruction listing. Expand real
binary/repository complexity after the smoke works, using owned/licensed inputs.

The initial automatic smoke is one repeat of B01, B04 and B08 per model, with
matched limits and clean workspaces. Then run the complete matrix within the
configured batch budget; report partial completion rather than bypassing caps.
Repeat seeds/counterbalanced order only after the basic paired run is stable.
Actions, model calls and guest jobs all have deterministic budgets. Every retry
and failed run counts. Stopping or denial is logged, not silently retried through
a broader permission set. Automatically reset guests between cases, collect
results, revoke credentials and release resources at the end or on failure.

Produce JSONL/CSV plus a readable local report. Separate task correctness,
schema/tool correctness, refusals, containment, performance and general-code
regression. Do not grade by how much damage a model can cause or provide public
targets. No self-propagation, external exploitation, real malware execution,
stealth persistence, real IP-rotation service or destructive dead-man action.
Increasing difficulty means harder owned tasks and failure/recovery scenarios
inside the proven boundary; widening scope requires an explicit new task.

## E. Acceptance and return

Test starter code; implement and test actual VM transport/watchdog/relay/cleanup;
prove the allowed path AND denied paths; prove budgets survive a killed controller;
verify fresh snapshots and the paired model identities; run actual local smoke.
Recheck host desktop, ordinary internet, firewall and normal Hermes/model recovery.
Do not expose a new dashboard to LAN/WAN. A CLI plus local artifacts is sufficient.

Produce ONE sanitized review ZIP per RETURN_CONTRACT.md. Include exact source
commit/config/artifact hashes, observed controls, measured trials, reproducible
commands, remaining gaps and rollback. Preserve any logs containing generated
lab tokens privately; omit keys/secrets/IPs/private source data from the return.
Any omitted live stage is explicitly blocked/unverified. Complete everything
independent of a blocked model or GPU window and preserve a runnable next step.
