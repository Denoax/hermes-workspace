type Conversation = { id: string; title: string; project: string | null };
type Changes = { title: string; project: string | null };
type ManagementApi = {
  rename: (id: string, title: string) => Promise<unknown>;
  move: (id: string, project: string | null) => Promise<unknown>;
};

/** Only an explicit Save persists the captured row target's staged changes.
 * Existing rename/move endpoints remain authoritative; failures propagate so a
 * partially saved rename is not reported as an atomic rollback or success. */
export async function saveManagedConversation<T extends Conversation>(target: T,
  changes: Changes, api: ManagementApi): Promise<T> {
  const title = changes.title.trim();
  if (!target.id || !title || title.length > 80) throw Error("Conversation name must contain 1–80 characters.");
  const project = changes.project;
  if (title !== target.title) await api.rename(target.id, title);
  if (project !== target.project) await api.move(target.id, project);
  return { ...target, title, project };
}
