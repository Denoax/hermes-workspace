export type CitationSource = {
  id: string;
  title: string;
  url: string;
  snippet?: string;
};
type Node = {
  type: string;
  value?: string;
  url?: string;
  children?: Node[];
  data?: { hProperties: Record<string, string | number> };
};
type SearchAttachment = { metadata: { search?: { sources: unknown } } };
type SearchEvent = { run_id: string; type: string; sources?: unknown };

/** The only installed search provider supplies canonical public Wikipedia URLs. */
function publicSource(value: unknown): CitationSource | null {
  if (!value || typeof value !== "object") return null;
  const source = value as Record<string, unknown>;
  if (
    typeof source.id !== "string" ||
    !source.id ||
    source.id.length > 128 ||
    typeof source.title !== "string" ||
    !source.title.trim() ||
    typeof source.url !== "string"
  )
    return null;
  try {
    const url = new URL(source.url);
    if (
      url.protocol !== "https:" ||
      url.hostname !== "en.wikipedia.org" ||
      url.port ||
      url.username ||
      url.password
    )
      return null;
    return {
      id: source.id,
      title: source.title,
      url: url.href,
      snippet:
        typeof source.text === "string"
          ? source.text
          : typeof source.snippet === "string"
            ? source.snippet
            : undefined,
    };
  } catch {
    return null;
  }
}
function sourceGroup(value: unknown): CitationSource[] | null {
  if (!Array.isArray(value) || !value.length || value.length > 4) return null;
  const result = value.map(publicSource);
  // Never compact a malformed group: that would shift the model's [n] indexes.
  return result.every((source): source is CitationSource => source !== null)
    ? result
    : null;
}
/** Bind previews to the actual turn, never to a later global search panel. */
export function turnCitationSources(
  attachments: SearchAttachment[] | undefined,
  events: SearchEvent[],
  runId: string | undefined,
): CitationSource[] {
  if (!runId) return [];
  const groups: unknown[] = (attachments ?? []).flatMap((item) =>
    item.metadata.search ? [item.metadata.search.sources] : [],
  );
  groups.push(
    ...events
      .filter((event) => event.run_id === runId && event.type === "search")
      .map((event) => event.sources),
  );
  const distinct = new Map<string, CitationSource[]>();
  for (const raw of groups) {
    const group = sourceGroup(raw);
    if (!group) return [];
    distinct.set(
      JSON.stringify(group.map((source) => [source.id, source.url])),
      group,
    );
  }
  // Separate attached search documents each number their sources from 1. With
  // different groups the assistant's [n] is ambiguous; keep its literal text.
  return distinct.size === 1 ? [...distinct.values()][0] : [];
}

/** Mark only generated, verified citation links; ordinary Markdown links stay ordinary. */
export function sourceCitations(sources: CitationSource[]) {
  const verified = sourceGroup(sources) ?? [];
  return function plugin() {
    return function transform(tree: unknown) {
      const pending = [tree as Node];
      while (pending.length) {
        const node = pending.pop()!;
        if (
          !node.children ||
          ["code", "inlineCode", "link", "linkReference"].includes(node.type)
        )
          continue;
        node.children = node.children.flatMap((child) => {
          if (child.type !== "text" || !child.value) return [child];
          const text = child.value,
            output: Node[] = [];
          let cursor = 0;
          for (const match of text.matchAll(/\[(\d{1,2})\]/g)) {
            const index = Number(match[1]),
              source = verified[index - 1];
            if (!source) continue;
            if (match.index! > cursor)
              output.push({
                type: "text",
                value: text.slice(cursor, match.index),
              });
            output.push({
              type: "link",
              url: source.url,
              children: [{ type: "text", value: match[0] }],
              data: {
                hProperties: {
                  "data-hermes-citation-index": index,
                  "data-hermes-source-id": source.id,
                },
              },
            });
            cursor = match.index! + match[0].length;
          }
          if (!cursor) return [child];
          if (cursor < text.length)
            output.push({ type: "text", value: text.slice(cursor) });
          return output;
        });
        pending.push(...node.children);
      }
    };
  };
}
export function verifiedCitation(
  sources: CitationSource[],
  index: unknown,
  id: unknown,
  href: unknown,
): { source: CitationSource; index: number } | null {
  const number =
    typeof index === "number"
      ? index
      : typeof index === "string" && /^[1-4]$/.test(index)
        ? Number(index)
        : NaN;
  if (!Number.isInteger(number) || number < 1 || number > 4) return null;
  const source = publicSource(sources[number - 1]);
  return source && source.id === id && source.url === href
    ? { source, index: number }
    : null;
}
