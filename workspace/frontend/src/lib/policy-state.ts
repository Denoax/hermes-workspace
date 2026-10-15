type VersionedPolicy = { session_id: string | null; version: number };
/** Server policy versions prevent an older read from undoing a visible revoke. */
export function keepNewerPolicy<T extends VersionedPolicy>(
  current: T | null,
  next: T,
): T {
  return current?.session_id === next.session_id &&
    current.version > next.version
    ? current
    : next;
}
