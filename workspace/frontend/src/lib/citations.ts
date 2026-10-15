type Source = { url: string };
type Node = { type: string; value?: string; url?: string; children?: Node[] };

/** Link only citations backed by this turn's actual search sources. */
export function sourceCitations(sources: Source[]) {
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
            const source = sources[Number(match[1]) - 1];
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
