# Durable, bounded continuation

Read and apply `$reference-led-design`. Caching does not preserve a forgotten
requirement; compaction is not an unlimited context window. The durable contract
lives in files that each fresh executor reads. This implements that bookkeeping
and an optional finite CLI controller; it does not remove provider limits.

## Default: current interactive Codex

Integrate the prepared source and use the existing session as the sole writer.
At cycle start read project instructions, the ledger, PLAN/RESUME and git status.
Select one actionable task. Implement, verify affected behavior, record evidence
with relevant source hashes, update PLAN and checkpoint. A large task can stay
IN_PROGRESS/VERIFY across several cycles. Preserve the complete inventory.

```
python3 scripts/loopctl.py validate
python3 scripts/loopctl.py next
python3 scripts/loopctl.py checkpoint
```

Resume after interruption by reading those files and actual changes, rather than
asking the user to restate the requirements. Never overwrite an existing ledger
or rebase its scope silently. The candidate imports v4's measured statuses as a
historical baseline with exact row mappings. Archive verification and prepared
tool tests have scoped evidence; current native and visual work is not pre-passed.

`DONE` requires the specified evidence kinds, non-fixture live evidence where
needed, artifact hashes, current dependency hashes and appropriate scope fields.
Stale evidence stops selection. A screenshot's metadata cannot prove it is true;
read the artifact and assess the check. User approval is a real external message,
not editable JSON authority. The utility cannot authenticate its author.

## Optional: exclusive CLI batch

The implemented `scripts/looprun.py` is opt-in. Its tests use clearly synthetic
CLI events and real owned subprocesses; no provider agent was launched here.
Before native adoption, verify installed help/version, login/config and actual
sandbox behavior. Prove a harmless repository-only interrupted cycle without
model inference or privilege. Preserve the user's selected model/configuration.

```
python3 scripts/looprun.py
```

Without `--run` this only inspects the ledger and next task; it launches no CLI.
After the interactive writer has stopped, the native operator may start:

```
python3 scripts/looprun.py --run --exclusive-writer
```

The explicit exclusive-writer flag is an attestation, not proof that another
editor is idle. The Linux advisory lock excludes this controller's other batches;
it cannot stop unrelated editors. Never run two implementation writers together.

Each cycle starts `codex exec --json --sandbox workspace-write -` with a compact
stdin hydration prompt and fresh context. It does not override the model, ignore
configuration/rules, resume an unrelated last thread or add approval-bypass flags.
Read-only is an available diagnostic mode. Native authentication, GPU windows,
publication, deployment and reboot are outside the automatic runner's prompt.
Do them only through the current authorized native workflow and record results.

Defaults: at most eight cycles, 60 minutes for the batch, 20 minutes per cycle,
two consecutive cycles without newly validated completed-task evidence, and
8 MiB combined output per cycle. Invalid ledgers, changed scope, CLI errors,
timeouts or malformed events stop the batch. A successful CLI turn is only
process completion; it is never the release completion condition.

The runner records failures, checkpoints valid current state on exit/interruption,
and terminates only its own created process group. Private logs are under
`.agent/hermes-loop/runtime/`, ignored by Git, owner-only directory access; they
may include sensitive CLI output and must not enter the review ZIP. Ctrl-C stops
the owned cycle. Later resume reruns the command after inspecting RESUME/git
status. Budgets deliberately require a new finite batch rather than an endless
automatic restart. If the last process died before checkpoint, hydrate the
actual diff first and repair the state without discarding edits.

All-DONE produces `REVIEW_COMPLETION_CLAIM`, never an automatic quality/human
approval. Manual-ready work produces `WAIT_FOR_USER`; other blocked work produces
`REPLAN_BLOCKED_WORK`. Both preserve the remaining IDs and stop the controller.
An implementation fault in the controller can only be debugged as code; changing
a JSON result to PASS does not repair it.

## Primary sources

- [OpenAI non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode), verified 15 October 2026, establishes JSONL execution and workspace-write sandbox selection. Installed CLI compatibility remains a native prerequisite.
- [OpenAI long-horizon tasks](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) supports milestone planning and persistent validation records.
- [Anthropic effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) and [long-running app harnesses](https://www.anthropic.com/engineering/harness-design-long-running-apps) motivate incremental progress records and separate evaluation. This package uses one implementation writer and a distinct review phase.
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) and [compaction](https://developers.openai.com/api/docs/guides/compaction) concern different context/runtime mechanisms; neither is a substitute for the external task contract.
