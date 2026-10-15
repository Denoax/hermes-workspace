# Earlier lab and operator notes

Preserved from the pre-presentation README. Historical receipts and limits below are not new qualification results. For the current interface, start with the root README.

# Workspace continuation

The current workspace implementation and operating constraints are in [workspace/README.md](../workspace/README.md). The prior lab measurements and adverse results below remain historical evidence. Current native qualification and live acceptance must be reported separately; source/test completion alone is not VM/model proof.

# Mani Hermes isolated VM lab

The automated lab boots three isolated KVM guests, installs pinned Hermes offline,
runs bounded local inference against both pinned model artifacts, grades answers
outside the guests, and cleans owned resources. Actual confinement, network, VM
watchdog, model-compute cancellation and normal-Qwen recovery receipts are included.
Tool workers and router integration remain unfinished. Requirement documents are
guidance; measured receipts establish what actually ran. See the review report for
correctness scores and acceptance gaps.

Use the native operator environment: the Flatpak tool environment hides native KVM/systemd/GPU
and changes its view of root ownership. No host-control Python dependencies are
needed. When the supervisor is stopped after recovery, `doctor` reports its
protected control channel unavailable and stage checks fail closed. This does not
invalidate historical signed-image or live qualification receipts. For a VM-only
session, start the installed supervisor in the native terminal before provisioning:

```sh
sudo /usr/bin/systemctl start mani-vmlab-supervisor.service
```

Model inference additionally needs an explicitly selected bounded GPU window and
the installed fixed native helper. The protected supervisor accepts only fixed operator operations;
no guest/model selects a host executable, PID, unit or path.

```sh
python3 -B labctl doctor
python3 -B labctl provision --dry-run
python3 -B labctl provision
python3 -B labctl qualify --run-id RUN_ID
python3 -B labctl stop --run-id RUN_ID
python3 -B labctl cleanup --run-id RUN_ID
python3 -B scripts/validate.py --integration
```

`provision` starts three no-agent KVM VMs from a signed, pinned Ubuntu image,
using dedicated nonroot QEMU, private network/IPC namespaces, an empty home,
narrow read-only image/seed binds, pinned SSH through owned UNIX sockets, and
cgroup CPU/RAM/PID/I/O limits. Actual tests in `results/continuation` verified
absence of personal home, Docker/GPU devices, capabilities and unbounded memory.
The canary proof covers owned synthetic namespaces. Current PC Bunker inet
input/forward default-drop policy was observed separately; physical LAN/WAN
ingress remains unverified. The lab did not change that firewall policy.

Five actual outside observers verified deadline, heartbeat-loss, VM-crash,
owner-crash and frozen-supervisor termination and recorded-inode cleanup.
The signed base and evidence are retained. A failed startup returns its run ID
and cleanup result. Always retain diagnostic failures; a source flag is not proof.

The relay remains text-only, nonstreaming, quota/replay bounded and fixed-backend.
Guest Hermes is pinned to revision `63279301bcbdc185c1b07b98a9312eb0c862f26d`;
62 CPython 3.12 Linux wheels were fetched against its hash-locked dependencies.
Offline installation/import, real main-model requests and compute cancellation
are proven. Unused auxiliary tasks are configured or disabled; independent live
auxiliary/delegation/tool-worker coverage remains incomplete.
Do not invoke `guest/solve.py` on the personal host.

The 21,166,758,656-byte candidate GGUF was acquired as data and matches its pinned
LFS SHA-256. Architecture, tokenizer family, chat-template hash and quantization
kind match the normal artifact's selected metadata. Full vocabulary, merges and
special-token IDs match. The normal artifact explicitly sets add_bos_token=false;
the candidate omits it. The effective add-special-token probes matched on both
loaded artifacts. Both models loaded in the confined lab backend at context 8192.
The derivative's exact base-weight revision is undocumented; this is an artifact
comparison, and its legacy license-name inconsistency is retained in provenance.

Native setup changed the PC during the user-selected maintenance window: the
package cache was preserved on /home, 98 old upgrade versions were signature
verified, the package DB was backed up, and a supported full Arch transaction
installed/upgraded 118 packages. Normal Hermes/Qwen configuration and original
service PIDs remained unchanged. The user completed a native reboot; loaded NVIDIA and userspace now agree at
615.78.08. Quickshell's Qt update was repaired with the same-source hardened compatibility
rebuild; its installed binary passes the Qt check. The installed compatibility check passes after reboot. Physical desktop approval
remains unverified.
No automatic reboot has occurred. See `native/OPERATIONS.md` for recovery.

Read/apply the installed `reference-led-design` skill, with the bundled snapshot
as fallback. This is nonvisual lab work: inspect primary technical sources,
produce no generated visual media, and distinguish runtime evidence from tests.

The model parser uses its own `mani-vmlab-model` account (UID/GID 958), separate
from QEMU's UID/GID 959. Its measured 8,192-context service has a thin root, pinned
read-only weights/runtime, a private network namespace, and only an owned Unix API.
A separate system-manager window guard has a 30-minute deadline and 45-second
operator-heartbeat bound. It temporarily masks only normal Qwen, validates the
mask identity, and restores its original 65,536-context service after stopping the
lab. Actual owner-crash and natural-expiry recovery are measured. Early interrupted
boots, competing-service load, observer/shutdown failures, protocol errors and an
expired-window partial run are retained as historical evidence, never folded into
the corrected paired result.
`native/run_smoke.py` is a fixed trusted orchestrator, not a root agent: it accepts
only `run` or explicitly authorized `run-new-window`, sends fixed synthetic cases to nonroot guest Hermes, grades JSON outside
the guests, and never executes candidate code on the host. Native authentication
stages this reviewed helper under the protected setup directory.
`native/resume_smoke.py` applies hash-pinned corrections and runs that helper.
`scripts/import_smoke_receipt.py` verifies root ownership, independently grades
model-bound answers and exports JSONL/CSV with missing cases explicitly unscored.

The current continuation adapter accepts only `reasoning_effort="none"` and maps
it to the pinned backend's thinking switch. The guest keeps every request at the
same 1,024-token cap, including Hermes continuations. Reports sum all completed
request usage. Seed 41, temperature 0, top-p 1 and fixed normal-then-candidate order
are shared. Case wall time includes guest startup; whole-device VRAM samples and
process RSS high-water are not isolated continuous peaks. These tiny synthetic
samples do not establish intelligence, causal abliteration effects or refusal rates.

The native helper completes B01/B04/B08 on each artifact, then admits the 24-trial
matrix only if all six answers pass strict grading. `results/smoke` is the latest
imported paired run; `results/matrix` explicitly records cases withheld by the gate.
Named history directories and dated receipts retain adverse attempts. Top-level
initial audit/command records and `results/run` belong to the first blocked delivery,
not current runtime status. `labctl report` includes imported native matrix results.

Rebuild the installed 22-file source pack without executing it:

```sh
python3 -B scripts/prepare_native_runtime.py /PRIVATE/NEW/runtime-source.zip
```

The byte hash and source file hashes are in `SOURCE_VERSION.json` in the review.
Native installation needs protected authentication and the reviewed fixed helpers;
never run guest solvers or model-generated code on the personal host.
