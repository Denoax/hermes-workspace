type Folder = { id: string; parent: string | null; label: string };
/** Keep a matching branch's context while rendering every folder exactly once. */
export function folderTree<T extends Folder>(
  folders: T[],
  query: string,
): { roots: T[]; children: Map<string, T[]> } {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const children = new Map<string, T[]>();
  for (const folder of folders)
    if (folder.parent && byId.has(folder.parent))
      children.set(folder.parent, [
        ...(children.get(folder.parent) ?? []),
        folder,
      ]);
  const term = query.trim().toLocaleLowerCase(),
    included = new Set<string>(),
    descended = new Set<string>();
  function includeDescendants(folder: T) {
    if (descended.has(folder.id)) return;
    descended.add(folder.id);
    included.add(folder.id);
    for (const child of children.get(folder.id) ?? [])
      includeDescendants(child);
  }
  for (const folder of folders) {
    if (term && !folder.label.toLocaleLowerCase().includes(term)) continue;
    includeDescendants(folder);
    let parent = folder.parent;
    const visited = new Set<string>();
    while (parent && !visited.has(parent)) {
      visited.add(parent);
      const ancestor = byId.get(parent);
      if (!ancestor) break;
      included.add(parent);
      parent = ancestor.parent;
    }
  }
  return {
    roots: folders.filter(
      (folder) =>
        included.has(folder.id) &&
        (!folder.parent || !included.has(folder.parent)),
    ),
    children: new Map(
      [...children].map(([id, rows]) => [
        id,
        rows.filter((folder) => included.has(folder.id)),
      ]),
    ),
  };
}
