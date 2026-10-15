# v4 verification scope

Measured on the configured workstation on 2026-10-15, using the existing Hermes
desktop pin, dedicated browser profile, production catalog and port 18791.
Isolated servers and direct model requests are not counted as production replies.

- Both installed local models completed three connected turns with contextual
  recall and reload continuity. A later normal → candidate → normal sequence also
  passed after selective test cleanup.
- Real output streamed. Cancel acknowledged in 0.170 seconds, retained partial
  text and left the normal backend idle. A real service interruption produced an
  actionable preserved-turn error; same-ID retry completed without duplicates.
- Actual approval cards denied, allowed once, granted a narrow read, revoked and
  replayed safely. Qwen proposed a file read, waited for approval, and used the
  returned contents in its next reply. Boundary fixtures cover expiry, stale
  bases, concurrent claims and late results after cancellation/revocation.
- Five accepted WAV files are byte-identical to the pre-v4 snapshot. Actual
  microphone checks captured 1.54 seconds cumulatively, released all tracks and
  uploaded no private audio. A separately pinned public speech sample passed
  real upload and local CPU transcription; that sample is not redistributed.
- Rendered desktop/portrait, both themes, reduced motion and forced-colors
  emulation were inspected. Nine native synthesized pointer targets passed.
  An unedited app-window recording contains 542 frames over 9.03 seconds.

## Remaining limits

The full current-boot watchdog qualification is **blocked**. Two aggregate runs
failed before their triggers because controller readiness exhausted the existing
boot attempts. A separate three-VM diagnostic boot succeeded, and one standalone
deadline scenario stopped all three real VMs within 2.30 seconds with clean
teardown. Those narrower successes do not replace the aggregate receipt.
Qualified guest execution and its task-result animation therefore remain
unavailable. No timeout, admission check or qualification receipt was weakened.

Human continuous-motion approval, a new physical sound audition, physical speech
quality, unplug behavior, assistive technology, alternate browsers, high-refresh
presentation and reboot recovery are not established by these checks. The
candidate's pinned bytes are verified; its upstream ablation lineage remains
unproven. This is functional verification, not a model-quality benchmark.

The complete private review archive includes scoped acceptance results, retained
adverse evidence, hashes, motion evidence and rollback instructions. It excludes
the catalog, credentials, comparison media and rollback backups. Native rollback
is fingerprint-gated; see [production operation](PRODUCTION_V4.md).
