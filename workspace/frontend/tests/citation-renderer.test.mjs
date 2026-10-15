// Server-rendered component fixture only; actual hover/focus behavior requires the production browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
const result = await build({
  stdin: {
    contents:
      'import {createElement} from "react"; import {renderToStaticMarkup} from "react-dom/server"; import {MessageMarkdown} from "./src/MessageMarkdown"; export const render=(text,sources)=>renderToStaticMarkup(createElement(MessageMarkdown,{text,sources})); export const renderPair=(first,second)=>renderToStaticMarkup(createElement("section",null,createElement(MessageMarkdown,first),createElement(MessageMarkdown,second)));',
    resolveDir: process.cwd(),
    loader: "tsx",
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "cjs",
});
const module = { exports: {} };
new Function("require", "module", "exports", result.outputFiles[0].text)(
  createRequire(import.meta.url),
  module,
  module.exports,
);
const { render, renderPair } = module.exports;
const sources = [
  {
    id: "42",
    title: "Example",
    url: "https://en.wikipedia.org/wiki/Example",
    snippet: "Supplied extract",
  },
];
test("a verified assistant citation mounts the original chip with actual source label and href", () => {
  const html = render("A sourced answer [1]. Unknown [9].", sources);
  assert.equal(
    (html.match(/data-slot="web-search-citation"/g) ?? []).length,
    1,
  );
  assert.ok(html.includes('aria-label="Example, en.wikipedia.org"'));
  assert.ok(html.includes('href="https://en.wikipedia.org/wiki/Example"'));
  assert.ok(html.includes("Unknown [9]"));
  assert.ok(!html.includes('data-slot="web-search-answer"'));
  assert.ok(!html.includes("data-writing="));
});
test("ordinary model links, raw HTML and code cannot forge an inline preview", () => {
  const html = render(
    'Ordinary [1](https://en.wikipedia.org/wiki/Example), `code [1]`. <a data-hermes-citation-index="1" data-hermes-source-id="42">raw</a>',
    sources,
  );
  assert.ok(!html.includes('data-slot="web-search-citation"'));
  assert.ok(html.includes("<code>code [1]</code>"));
});
test("the existing Markdown unsafe-link transform remains active", () => {
  const html = render("[unsafe](javascript:alert(1))", sources);
  assert.ok(!html.includes("javascript:"));
  assert.ok(!html.includes('data-slot="web-search-citation"'));
});

// Context is per message and must update without capturing an earlier source
// group. Native hover/focus continuity is checked in the actual preview probe.
test("adjacent messages resolve the same citation number within their own source groups", () => {
  const other = [{ id: "84", title: "Second", url: "https://en.wikipedia.org/wiki/Second" }];
  const html = renderPair({ text: "First [1]", sources }, { text: "Second [1]", sources: other });
  assert.equal((html.match(/data-slot="web-search-citation"/g) ?? []).length, 2);
  assert.ok(html.indexOf('aria-label="Example, en.wikipedia.org"') < html.indexOf('aria-label="Second, en.wikipedia.org"'));
  assert.equal((html.match(/href="https:\/\/en.wikipedia.org\/wiki\/Example"/g) ?? []).length, 1);
  assert.equal((html.match(/href="https:\/\/en.wikipedia.org\/wiki\/Second"/g) ?? []).length, 1);
});
test("fresh equivalent metadata and later source groups never reuse stale destinations", () => {
  const first = render("Claim [1]", sources.map((source) => ({ ...source })));
  const next = render("Claim [1]", [{ id: "85", title: "Replacement", url: "https://en.wikipedia.org/wiki/Replacement" }]);
  assert.ok(first.includes('href="https://en.wikipedia.org/wiki/Example"'));
  assert.ok(next.includes('href="https://en.wikipedia.org/wiki/Replacement"'));
  assert.ok(!next.includes('href="https://en.wikipedia.org/wiki/Example"'));
});
test("invalid metadata in one message cannot borrow a sibling message's valid source", () => {
  const html = renderPair({ text: "Valid [1]", sources }, { text: "Unverified [1]", sources: [{ id: "42", title: "Injected", url: "https://example.com/private" }] });
  assert.equal((html.match(/data-slot="web-search-citation"/g) ?? []).length, 1);
  assert.ok(html.includes("Unverified [1]"));
  assert.ok(!html.includes('href="https://example.com/private"'));
});
