import { createContext, useContext, type ComponentProps } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import { WebSearchCitation } from "./components/web-search";
import {
  sourceCitations,
  verifiedCitation,
  type CitationSource,
} from "./lib/citations";

const CitationSources = createContext<CitationSource[]>([]);

function MarkdownLink({
  node,
  href,
  children,
  ...props
}: ComponentProps<"a"> & ExtraProps) {
  const sources = useContext(CitationSources);
  const citation = verifiedCitation(
    sources,
    node?.properties["data-hermes-citation-index"],
    node?.properties["data-hermes-source-id"],
    href,
  );
  return citation ? (
    <WebSearchCitation source={citation.source} index={citation.index} />
  ) : (
    <a {...props} href={href}>
      {children}
    </a>
  );
}

// Polling and streamed text may rerender Markdown. A stable renderer keeps the
// citation's hover timer, keyboard focus and open preview mounted across them;
// context supplies the current turn's sources without a stale closure.
const MARKDOWN_COMPONENTS: Components = { a: MarkdownLink };

export function MessageMarkdown({
  text,
  sources,
}: {
  text: string;
  sources: CitationSource[];
}) {
  return (
    <CitationSources.Provider value={sources}>
      <Markdown
        skipHtml
        remarkPlugins={[sourceCitations(sources)]}
        components={MARKDOWN_COMPONENTS}
      >
        {text}
      </Markdown>
    </CitationSources.Provider>
  );
}
