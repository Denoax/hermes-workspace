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
const { sourceCitations } = await import(
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
    { url: "https://en.wikipedia.org/wiki/Llama_(language_model)" },
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
  sourceCitations([{ url: "https://en.wikipedia.org/wiki/Example" }])()(tree);
  assert.deepEqual(tree, before);
});
