export type ManagementFailure = { epoch: number; message: string };

export function managementFailureMessage(error: unknown) {
  const detail = error instanceof Error ? error.message : String(error);
  if (/unknown_(session|project)|not_found/.test(detail))
    return "This item is no longer available. Close this dialog and choose another item.";
  return "Could not save changes: " + detail;
}

/** An earlier operation's error cannot replace a newer dialog's own feedback. */
export function ManagementError({ failure, epoch }: { failure: ManagementFailure | null; epoch: number }) {
  if (!failure || failure.epoch !== epoch) return null;
  return <p className="run-error management-error" role="alert">{failure.message}</p>;
}
