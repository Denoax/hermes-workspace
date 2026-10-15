import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/lib/run-receipts.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { applyCancellationResult } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
const requested = { id: "owned", created: 1, state: "generating" },
  receipt = { ...requested, state: "cancelling" };
test("a cancellation receipt uses the actual server state when the displayed attempt has not advanced", () => {
  assert.equal(
    applyCancellationResult(requested, requested, {
      ...receipt,
      state: "completed",
    }).state,
    "completed",
  );
});
test("terminal stream state arriving before a cancel RPC reply remains terminal", () => {
  for (const state of ["completed", "cancelled", "failed"]) {
    const current = { ...requested, state };
    assert.equal(applyCancellationResult(current, requested, receipt), current);
  }
});
test("a late cancellation reply never replaces a newly selected conversation", () => {
  const current = { id: "different", created: 1, state: "generating" };
  assert.equal(applyCancellationResult(current, requested, receipt), current);
});
test("same-ID retry attempts reject an old cancellation receipt", () => {
  const current = { ...requested, created: 2 };
  assert.equal(applyCancellationResult(current, requested, receipt), current);
});
test("newer nonterminal stream phases also take precedence over an older cancellation reply", () => {
  const current = { ...requested, state: "restoring" };
  assert.equal(applyCancellationResult(current, requested, receipt), current);
});
const { applyRetryResult } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
test("retry A's response cannot replace the run in newly selected conversation B", () => {
  const failed = { ...requested, state: "failed" },
    current = { id: "B", created: 3, state: "generating" };
  assert.equal(
    applyRetryResult(current, failed, {
      ...failed,
      state: "queued",
      created: 2,
    }),
    current,
  );
});
test("retry response accepts its new attempt only while the failed original attempt is still displayed", () => {
  const failed = { ...requested, state: "failed" },
    retried = { ...failed, state: "queued", created: 2 };
  assert.equal(applyRetryResult(failed, failed, retried), retried);
  assert.equal(applyRetryResult(retried, failed, retried), retried);
});
