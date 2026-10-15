# Automated Hermes VM research lab

HANDOFF TYPE: Local Codex implementation, with tested starter code and fixtures.
ASSET PACK REQUIRED: This complete ZIP. Model weights and OS images are NOT included.
Prepared 2026-10-12 for Mani's personal Arch/Hyprland PC.

Goal: automate provisioning, isolation checks, task dispatch, normal-vs-abliterated
Qwen comparisons, deterministic verification, safe shutdown/reset, and reporting.
The owned lab studies log analysis, recovery, code reasoning and agent containment.
It has no public targets and no autonomous public-internet access during experiments.

This is an implementation handoff, not a deployed VM fleet. Starter policy/grade
code and fixtures are runnable offline. Local Codex must implement the real VM,
Hermes, model relay, watchdog and lifecycle integrations and test them on the PC.
Passing starter tests does not prove VM isolation or any model's capability.

Download to `~/Downloads/MANI_HERMES_VM_LAB_Codex_Handoff_v1.zip`, compare its SHA-256
to the value in the ChatGPT response, and extract into a NEW private directory.
Read AGENTS.md, CODEX_TASK.md, ARCHITECTURE.md, MODEL_COMPARISON.md, SOURCE_NOTES.md
and RETURN_CONTRACT.md completely. Read/apply `$reference-led-design`; its complete
snapshot is bundled. If discovery fails, read the snapshot directly and continue.
No global skill change or visual work is part of this implementation.

Start only after the current PC-hardening transaction has finished. Do not let two
Codex sessions mutate networking/services simultaneously. Preparation and offline
tests can proceed while awaiting that dependency. Verify the resulting host state;
the hardening report is not a proof that arbitrary code is safe to execute.

Expected operator experience after local implementation:
`labctl doctor` -> `labctl provision` -> `labctl smoke` -> `labctl run --matrix ...`
-> automatically recorded results, cleanup and a review ZIP.
These commands are the required interface for Codex to build, not existing
commands claimed to be installed by this package.

No recurring schedule is configured. One invocation runs the requested matrix
within explicit budgets; additional runs remain operator-initiated.
