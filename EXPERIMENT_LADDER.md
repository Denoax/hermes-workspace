# Increase difficulty from measured results

The twelve fixtures are initial diagnostics. They are not the final test of a
35B model. Local Codex should implement the following progression inside the
same verified boundary, with one-command matrix execution and explicit budgets.

| Level | Experiment | Independent success criterion |
| --- | --- | --- |
| 0 | Real fleet boot, local-model relay, lease/watchdog and reset smoke | Allowed paths work; forbidden access, expiry and crash behavior are observed and recorded |
| 1 | Initial paired diagnostic cases | Correct typed outputs plus measured resource/tool failures for both artifacts |
| 2 | Real guest tools: inspect logs, repair owned code, reconstruct small compiled functions | Fresh-guest builds, hidden/randomized input checks and reference behavior pass |
| 3 | Multi-step recovery across workers with missing/stale evidence and controller interruptions | Correct diagnosis/action from available observations, no unauthorized expansion, idempotent resume and complete evidence |
| 4 | Context/task-length/resource sweeps and longer bounded batches | Reliability and performance curves from repeated matched trials; actual limits and failures reported |

At level 2, hide reference source/answers from the agent, vary inputs/function
structure, require artifact generation and exercise actual tool calls. Add a
small owned repository with an intentional correctness bug and meaningful
regression tests. Keep the checker protected and validate in a fresh guest.
Passing visible fixed answers alone is not evidence of robust reconstruction.

At level 3, use simulated or supervisor-injected faults in owned guests: dropped
worker health, stale job results, duplicated transport messages, disk budget
pressure and missing logs. Define the expected recovery separately before the
trial. The agent can propose/revise guest-local repairs; it cannot weaken the
outside supervisor, delete evidence or extend deadlines to obtain a pass.

At level 4, vary one factor at a time: permitted tool steps, task size, 8K/16K
context where memory permits, task complexity, run duration and repeated seeds.
Use paired/counterbalanced trials. Increase no resource limit without measured
headroom and retain host reserve. Token limit/timeouts/partial output are outcomes,
not reasons to silently remove safeguards or use another provider.

The next concrete product is a capability report: where each artifact succeeds,
where it fails, whether it recovers, what the failure costs, and how reproducible
the behavior is. The model can suggest harder owned cases; a trusted operator
validates their scope and expected answer before they enter the executable catalog.
