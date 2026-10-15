# Preparation verification

This package is a Codex implementation handoff, not a deployed fleet or a model
benchmark result. No VM, Hermes lab session, model download or inference run was
started during preparation. Source cards/docs were inspected; artifacts/revisions
and actual target-host capabilities remain for local execution.

46 offline starter tests passed, including:
- Authorized schema/scope and denial of host commands, caller paths, wrong tokens,
  unknown VMs/cases/actions, duplicates and malformed types.
- Absolute deadlines, heartbeat loss, revocation, clock anomalies and bounded,
  representable lease configuration.
- Atomic action quotas under concurrent requests and candidate UTF-8 byte caps.
- JSON byte/depth/duplicate-key/nonfinite-value limits; quoted brackets remain data.
- Strict answer grading, boolean/integer distinction, malformed/schema failures,
  catalog/answer consistency, unresolved model hashes and disabled example readiness.

Archive integrity, a clean extraction, exact copies of all six policy files and
the standalone module-based scorer are checked before delivery. Synthetic golden
answers used to test the grader are never represented as model-generated answers.
The reference lease gate does not start/stop VMs or enforce networking by itself;
the live acceptance matrix requires independent outside enforcement evidence.
