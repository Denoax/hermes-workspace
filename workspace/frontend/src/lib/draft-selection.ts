/** Browser selection references only. The server owns attachment bytes/metadata. */
export type DraftSelection = { version: 1; revision: string; ids: string[] };
export type SelectionStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;
const ID = /^[a-f0-9]{32}$/;
export function selectionKey(scope: string | null): string {
  if (scope !== null && !ID.test(scope))
    throw Error("Invalid conversation scope.");
  return "hermes:draft-attachments:v1:" + (scope ?? "new");
}
export function attachmentIds(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    value.length > 8 ||
    value.some((id) => typeof id !== "string" || !ID.test(id))
  )
    throw Error(
      "Saved attachment selection is invalid; clear it and attach the files again.",
    );
  return [...new Set(value as string[])];
}
export function readSelection(
  storage: SelectionStorage,
  scope: string | null,
): DraftSelection {
  const raw = storage.getItem(selectionKey(scope));
  if (raw === null) return { version: 1, revision: "", ids: [] };
  if (raw.length > 1024) throw Error("Saved attachment selection is invalid.");
  const value = JSON.parse(raw);
  if (
    !value ||
    value.version !== 1 ||
    typeof value.revision !== "string" ||
    !ID.test(value.revision) ||
    Object.keys(value).some(
      (key) => !["version", "revision", "ids"].includes(key),
    )
  )
    throw Error("Saved attachment selection is invalid.");
  return {
    version: 1,
    revision: value.revision,
    ids: attachmentIds(value.ids),
  };
}
export function sameSelection(a: DraftSelection, b: DraftSelection): boolean {
  return (
    a.revision === b.revision && JSON.stringify(a.ids) === JSON.stringify(b.ids)
  );
}
export function replaceSelection(
  storage: SelectionStorage,
  scope: string | null,
  expected: DraftSelection,
  ids: string[],
): DraftSelection | null {
  if (!sameSelection(readSelection(storage, scope), expected)) return null;
  const next: DraftSelection = {
    version: 1,
    revision: crypto.randomUUID().replaceAll("-", ""),
    ids: attachmentIds(ids),
  };
  storage.setItem(selectionKey(scope), JSON.stringify(next));
  return next;
}
export function clearInvalidSelection(
  storage: SelectionStorage,
  scope: string | null,
): DraftSelection {
  // An explicit user action clears only references, never attachment bytes.
  const next: DraftSelection = {
    version: 1,
    revision: crypto.randomUUID().replaceAll("-", ""),
    ids: [],
  };
  storage.setItem(selectionKey(scope), JSON.stringify(next));
  return next;
}
export function moveNewSelection(
  storage: SelectionStorage,
  destination: string,
): {
  from: DraftSelection;
  to: DraftSelection;
} {
  const from = readSelection(storage, null),
    target = readSelection(storage, destination);
  if (target.ids.length || target.revision !== "")
    throw Error("New conversation already has an attachment draft.");
  const to = replaceSelection(storage, destination, target, from.ids);
  if (!to || !replaceSelection(storage, null, from, []))
    throw Error("Attachment draft changed during conversation creation.");
  return { from, to };
}
export type AttachmentIssue = { id: string | null; message: string };
export async function restoreMetadata<T extends { id: string }>(
  ids: string[],
  get: (id: string) => Promise<T>,
): Promise<{
  items: T[];
  issues: AttachmentIssue[];
}> {
  const items: T[] = [],
    issues: AttachmentIssue[] = [];
  for (const id of attachmentIds(ids)) {
    try {
      const item = await get(id);
      if (!item || item.id !== id)
        throw Error("Attachment metadata identity mismatch.");
      items.push(item);
    } catch {
      issues.push({
        id,
        message:
          "An attachment is unavailable. Retry, or remove it and attach the file again.",
      });
    }
  }
  return { items, issues };
}

export type PromptDraft = { text: string; revision: number };
/** Equal text alone cannot identify an unchanged draft after edit/undo. */
export function samePrompt(
  current: PromptDraft | undefined,
  submitted: PromptDraft,
): boolean {
  return (
    !!current &&
    current.revision === submitted.revision &&
    current.text === submitted.text
  );
}
