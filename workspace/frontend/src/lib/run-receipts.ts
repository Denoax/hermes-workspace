type Run = { id: string; created: number; state: string };
const TERMINAL = new Set(["completed", "failed", "cancelled"]);
/** A delayed RPC reply cannot replace newer stream state or a different attempt. */
export function applyCancellationResult<T extends Run>(
  current: T | null,
  requested: T,
  receipt: T,
): T | null {
  if (
    !current ||
    current.id !== requested.id ||
    receipt.id !== requested.id ||
    current.created !== requested.created ||
    receipt.created !== requested.created ||
    current.state !== requested.state ||
    TERMINAL.has(current.state)
  )
    return current;
  return receipt;
}

/** Retry intentionally creates a new attempt but must stay in its original view. */
export function applyRetryResult<T extends Run>(
  current: T | null,
  requested: T,
  receipt: T,
): T | null {
  if (
    !current ||
    current.id !== requested.id ||
    receipt.id !== requested.id ||
    current.created !== requested.created ||
    current.state !== "failed"
  )
    return current;
  return receipt;
}
