type Run = { id: string; state: string };
type Event = {
  run_id: string;
  type: string;
  state?: string;
  label?: string;
  name?: string;
  lines?: number;
};
type Action = {
  state: string;
  type: string;
  resource: string;
  summary: string;
};
const labels: Record<string, string> = {
  queued: "Queued",
  searching: "Searching Wikipedia",
  admitting: "Loading local model",
  generating: "Working",
  cancelling: "Stopping compute",
  restoring: "Restoring normal Qwen",
  failed: "Response failed",
  completed: "Completed",
  cancelled: "Cancelled",
};
/** Presentation only; phase ownership stays with the run/action records. */
export function activityStatus(
  run: Run | null,
  events: Event[],
  actions: Action[],
  modelLabel: string,
  elapsed: number,
) {
  const current = run ? events.filter((event) => event.run_id === run.id) : [];
  const runLabel =
    current
      .filter((event) => event.type === "state" && event.state === run?.state)
      .at(-1)?.label ??
    (run ? (labels[run.state] ?? run.state.replaceAll("_", " ")) : "Working");
  if (run && !["failed", "completed", "cancelled"].includes(run.state)) {
    const file = current.filter((event) => event.type === "file").at(-1);
    return {
      visible: true,
      state: run.state,
      label: runLabel,
      runLabel,
      cancellable: true,
      context: file?.name
        ? `${file.name}${typeof file.lines === "number" ? ` · ${file.lines} lines` : ""}`
        : `${modelLabel} · ${elapsed}s elapsed`,
    };
  }
  const pending = actions.filter((action) => action.state === "pending").at(-1);
  if (pending)
    return {
      visible: true,
      state: "awaiting_approval",
      label: "Awaiting approval",
      runLabel,
      context: pending.resource || pending.summary,
      cancellable: false,
    };
  const executing = actions
    .filter((action) => action.state === "executing")
    .at(-1);
  if (executing)
    return {
      visible: true,
      state: "executing",
      label:
        executing.type === "guest.submit"
          ? "Dispatching guest task"
          : "Running approved action",
      runLabel,
      context: executing.resource || executing.summary,
      cancellable: false,
    };
  return {
    visible: run?.state === "failed",
    state: run?.state ?? "idle",
    label: runLabel,
    runLabel,
    context: modelLabel,
    cancellable: false,
  };
}
