import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/lib/draft-selection.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const {
  attachmentIds,
  selectionKey,
  readSelection,
  replaceSelection,
  clearInvalidSelection,
  moveNewSelection,
  restoreMetadata,
  sameSelection,
  samePrompt,
} = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
const a = "a".repeat(32),
  b = "b".repeat(32),
  c = "c".repeat(32),
  d = "d".repeat(32);
function storage() {
  const values = new Map();
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
test("persisted selection contains only a version, opaque revision and bounded unique IDs", () => {
  assert.deepEqual(attachmentIds([a, a, b]), [a, b]);
  for (const ids of [["../file"], Array(9).fill(a), [a.toUpperCase()]])
    assert.throws(() => attachmentIds(ids));
  const saved = storage();
  const next = replaceSelection(saved, c, readSelection(saved, c), [a, a, b]);
  assert.deepEqual(
    Object.keys(JSON.parse(saved.getItem(selectionKey(c)))).sort(),
    ["ids", "revision", "version"],
  );
  assert.match(next.revision, /^[a-f0-9]{32}$/);
  assert.deepEqual(readSelection(saved, c).ids, [a, b]);
  saved.setItem(
    selectionKey(c),
    JSON.stringify({ ...next, bytes: "not allowed" }),
  );
  assert.throws(() => readSelection(saved, c));
});
test("conversation selections remain isolated and new-draft migration preserves IDs before clearing its source", () => {
  const saved = storage();
  replaceSelection(saved, null, readSelection(saved, null), [a]);
  replaceSelection(saved, d, readSelection(saved, d), [b]);
  const moved = moveNewSelection(saved, c);
  assert.deepEqual(moved.from.ids, [a]);
  assert.deepEqual(readSelection(saved, c).ids, [a]);
  assert.deepEqual(readSelection(saved, null).ids, []);
  assert.deepEqual(readSelection(saved, d).ids, [b]);
  assert.throws(() => moveNewSelection(saved, c), /already has/);
});
test("an accepted old submit cannot clear a newer attachment selection", () => {
  const saved = storage(),
    initial = readSelection(saved, c);
  const submitted = replaceSelection(saved, c, initial, [a]);
  const followup = replaceSelection(saved, c, submitted, [b]);
  assert.equal(replaceSelection(saved, c, submitted, []), null);
  assert.ok(sameSelection(readSelection(saved, c), followup));
});
test("editing and undoing prompt text still protects the newer draft from old acceptance", () => {
  assert.equal(
    samePrompt({ text: "A", revision: 2 }, { text: "A", revision: 0 }),
    false,
  );
  assert.equal(
    samePrompt({ text: "B", revision: 1 }, { text: "A", revision: 0 }),
    false,
  );
  assert.equal(samePrompt(undefined, { text: "A", revision: 0 }), false);
  assert.equal(
    samePrompt({ text: "A", revision: 0 }, { text: "A", revision: 0 }),
    true,
  );
});
test("late upload CAS writes its captured conversation, never the newly selected conversation", () => {
  const saved = storage(),
    old = readSelection(saved, c);
  replaceSelection(saved, d, readSelection(saved, d), [b]);
  assert.ok(replaceSelection(saved, c, old, [a]));
  assert.deepEqual(readSelection(saved, c).ids, [a]);
  assert.deepEqual(readSelection(saved, d).ids, [b]);
});
test("explicit reset invalidates an old empty new-draft upload token even when IDs return to empty", () => {
  const saved = storage(),
    old = readSelection(saved, null);
  clearInvalidSelection(saved, null);
  assert.equal(replaceSelection(saved, null, old, [a]), null);
  assert.deepEqual(readSelection(saved, null).ids, []);
});
test("missing or mismatched server metadata remains visible as an issue rather than silently losing selection", async () => {
  const requested = [];
  const result = await restoreMetadata([a, b, c], async (id) => {
    requested.push(id);
    if (id === b) throw Error("404");
    return { id: id === c ? d : id, name: "server metadata" };
  });
  assert.deepEqual(requested, [a, b, c]);
  assert.deepEqual(
    result.items.map((item) => item.id),
    [a],
  );
  assert.deepEqual(
    result.issues.map((issue) => issue.id),
    [b, c],
  );
});
test("a metadata response arriving after scope switch cannot change either scope's stored references", async () => {
  const saved = storage();
  replaceSelection(saved, c, readSelection(saved, c), [a]);
  replaceSelection(saved, d, readSelection(saved, d), [b]);
  let release;
  const response = new Promise((resolve) => (release = resolve));
  const restoring = restoreMetadata(readSelection(saved, c).ids, async () => {
    await response;
    return { id: a };
  });
  replaceSelection(saved, d, readSelection(saved, d), [d]);
  release();
  await restoring;
  assert.deepEqual(readSelection(saved, c).ids, [a]);
  assert.deepEqual(readSelection(saved, d).ids, [d]);
});
