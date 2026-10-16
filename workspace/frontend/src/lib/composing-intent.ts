const KEY = "hermes-ui:composing-intent:v1";
const ID = /^[0-9a-f]{32}$/;
type Storage = Pick<globalThis.Storage, "getItem" | "setItem" | "removeItem">;
type View = { project_id?: string | null; session_id?: string | null } | null;
const projectId = (value: unknown): value is string | null => value === null || typeof value === "string" && ID.test(value);

/** Presentation-only intent never overrides the authenticated saved view. */
export function restoreComposingIntent(storage: Storage, view: View): boolean {
  if (view?.session_id != null) return false;
  const project = view?.project_id ?? null;
  if (!projectId(project)) return false;
  const raw = storage.getItem(KEY);
  if (!raw) return false;
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return false; }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return false;
  const value = parsed as Record<string, unknown>;
  return Object.keys(value).length === 2 && value.version === 1 &&
    projectId(value.project_id) && value.project_id === project;
}

export function saveComposingIntent(storage: Storage, view: View, composing: boolean) {
  const project = view?.project_id ?? null;
  if (!composing || view?.session_id != null || !projectId(project)) storage.removeItem(KEY);
  else storage.setItem(KEY, JSON.stringify({ version: 1, project_id: project }));
}
