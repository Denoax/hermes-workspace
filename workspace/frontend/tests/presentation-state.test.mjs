import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
async function load(path) {
  const built = await build({
    entryPoints: [path],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  return import(
    "data:text/javascript;base64," +
      Buffer.from(built.outputFiles[0].text).toString("base64")
  );
}
const { activityStatus } = await load("src/lib/activity-status.ts"),
  { folderTree } = await load("src/lib/folder-tree.ts");
test("active phase uses only its own run and matching state label", () => {
  const status = activityStatus(
    { id: "r", state: "restoring" },
    [
      { run_id: "old", type: "state", state: "restoring", label: "Wrong run" },
      { run_id: "r", type: "state", state: "generating", label: "Old phase" },
    ],
    [],
    "Normal Qwen",
    12,
  );
  assert.equal(status.label, "Restoring normal Qwen");
  assert.equal(status.context, "Normal Qwen · 12s elapsed");
  assert.equal(status.cancellable, true);
});
test("an active run takes precedence over a stale pending action; approval owns the HUD after the turn", () => {
  const action = {
    state: "pending",
    type: "workspace.write",
    resource: "program.py",
    summary: "Write file",
  };
  assert.equal(
    activityStatus({ id: "r", state: "generating" }, [], [action], "Qwen", 0)
      .state,
    "generating",
  );
  const approval = activityStatus(
    { id: "r", state: "completed" },
    [],
    [action],
    "Qwen",
    0,
  );
  assert.equal(approval.label, "Awaiting approval");
  assert.equal(approval.context, "program.py");
  assert.equal(approval.cancellable, false);
});
test("guest dispatch is labelled as admission work, never as a completed guest result", () => {
  const status = activityStatus(
    null,
    [],
    [
      {
        state: "executing",
        type: "guest.submit",
        resource: "Reviewed snapshot",
        summary: "Guest task",
      },
    ],
    "Qwen",
    0,
  );
  assert.equal(status.label, "Dispatching guest task");
  assert.equal(status.cancellable, false);
  assert.equal(
    activityStatus(
      null,
      [],
      [
        {
          state: "completed",
          type: "guest.submit",
          resource: "snapshot",
          summary: "Guest task",
        },
      ],
      "Qwen",
      0,
    ).visible,
    false,
  );
});
test("failed response remains an actual visible terminal status", () => {
  assert.equal(
    activityStatus({ id: "r", state: "failed" }, [], [], "Qwen", 0).label,
    "Response failed",
  );
});
const folders = [
  { id: "p", parent: null, label: "Owned parent" },
  { id: "c", parent: "p", label: "Owned child" },
  { id: "g", parent: "c", label: "Owned grandchild" },
  { id: "s", parent: "p", label: "Sibling" },
  { id: "private", parent: null, label: "Other project" },
];
function flatten(tree) {
  const rows = [];
  function visit(row, depth) {
    rows.push([row.id, depth]);
    for (const child of tree.children.get(row.id) ?? [])
      visit(child, depth + 1);
  }
  for (const root of tree.roots) visit(root, 0);
  return rows;
}
test("matching parent and child render once at their real depths and exclude unrelated roots", () => {
  assert.deepEqual(flatten(folderTree(folders, "Owned")), [
    ["p", 0],
    ["c", 1],
    ["g", 2],
    ["s", 1],
  ]);
});
test("a child-only match keeps ancestors and descendants without unrelated siblings", () => {
  assert.deepEqual(flatten(folderTree(folders, "child")), [
    ["p", 0],
    ["c", 1],
    ["g", 2],
  ]);
});
test("a matching parent includes all children even if a child appeared first in source order", () => {
  assert.deepEqual(
    flatten(
      folderTree([folders[1], folders[2], folders[0], folders[3]], "Owned"),
    ),
    [
      ["p", 0],
      ["c", 1],
      ["g", 2],
      ["s", 1],
    ],
  );
});
