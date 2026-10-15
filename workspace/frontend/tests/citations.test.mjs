import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/lib/citations.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { sourceCitations, turnCitationSources, verifiedCitation } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
test("a numbered citation resolves only to its actual supplied source", () => {
  const tree = {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [{ type: "text", value: "Result [1]; unknown [9]." }],
      },
    ],
  };
  sourceCitations([
    {
      id: "1337",
      title: "Llama",
      url: "https://en.wikipedia.org/wiki/Llama_(language_model)",
    },
  ])()(tree);
  const children = tree.children[0].children;
  assert.equal(children[1].type, "link");
  assert.equal(
    children[1].url,
    "https://en.wikipedia.org/wiki/Llama_(language_model)",
  );
  assert.equal(children[2].value, "; unknown [9].");
});
test("code and existing links retain their literal content", () => {
  const tree = {
    type: "root",
    children: [
      { type: "code", value: "[1]" },
      {
        type: "paragraph",
        children: [
          { type: "inlineCode", value: "[1]" },
          {
            type: "link",
            url: "https://example.org",
            children: [{ type: "text", value: "[1]" }],
          },
        ],
      },
    ],
  };
  const before = structuredClone(tree);
  sourceCitations([
    {
      id: "42",
      title: "Example",
      url: "https://en.wikipedia.org/wiki/Example",
    },
  ])()(tree);
  assert.deepEqual(tree, before);
});
const source = (id = "42", title = "Example") => ({
  id,
  title,
  url: "https://en.wikipedia.org/wiki/" + title,
  text: "Actual supplied search extract",
});
test("only the answer's actual turn attachments or run-matched search event supply previews", () => {
  const a = source();
  assert.deepEqual(
    turnCitationSources(
      undefined,
      [{ run_id: "other", type: "search", sources: [a] }],
      "owned",
    ),
    [],
  );
  assert.equal(
    turnCitationSources(
      [{ metadata: { search: { sources: [a] } } }],
      [],
      "owned",
    )[0].id,
    "42",
  );
  assert.equal(
    turnCitationSources(
      undefined,
      [{ run_id: "owned", type: "search", sources: [a] }],
      "owned",
    )[0].snippet,
    a.text,
  );
  assert.deepEqual(
    turnCitationSources(
      [{ metadata: { search: { sources: [a] } } }],
      [],
      undefined,
    ),
    [],
  );
});
test("duplicate observations of one source group resolve; independently numbered different groups remain literal", () => {
  const a = source(),
    b = source("90", "Other");
  assert.equal(
    turnCitationSources(
      [{ metadata: { search: { sources: [a] } } }],
      [{ run_id: "r", type: "search", sources: [a] }],
      "r",
    ).length,
    1,
  );
  assert.deepEqual(
    turnCitationSources(
      [
        { metadata: { search: { sources: [a] } } },
        { metadata: { search: { sources: [b] } } },
      ],
      [],
      "r",
    ),
    [],
  );
});
test("invalid source URLs never receive preview authority or shift another source's number", () => {
  for (const url of [
    "javascript:alert(1)",
    "http://en.wikipedia.org/wiki/Example",
    "https://evil.example/wiki/Example",
    "https://name:password@en.wikipedia.org/wiki/Example",
  ]) {
    const bad = { ...source(), url },
      tree = {
        type: "paragraph",
        children: [{ type: "text", value: "[1] [2]" }],
      };
    sourceCitations([bad, source("90", "Other")])()(tree);
    assert.deepEqual(tree.children, [{ type: "text", value: "[1] [2]" }]);
  }
});
test("renderer recognition requires the generated number, actual source ID and sanitized exact destination", () => {
  const sources = [source()];
  assert.equal(
    verifiedCitation(sources, 1, "42", sources[0].url).source.id,
    "42",
  );
  assert.equal(verifiedCitation(sources, 1, "wrong", sources[0].url), null);
  assert.equal(
    verifiedCitation(sources, 1, "42", "https://evil.example"),
    null,
  );
  assert.equal(verifiedCitation(sources, 9, "42", sources[0].url), null);
});
