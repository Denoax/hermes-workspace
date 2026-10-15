import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/lib/policy-state.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { keepNewerPolicy } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
test("an older allow read cannot overwrite a newer microphone revoke response", () => {
  const revoked = { session_id: "A", version: 3, microphone: false };
  assert.equal(
    keepNewerPolicy(revoked, { session_id: "A", version: 2, microphone: true }),
    revoked,
  );
});
test("a current version or different conversation receives its own server policy", () => {
  const prior = { session_id: "A", version: 3, microphone: false },
    other = { session_id: "B", version: 1, microphone: false },
    newer = { session_id: "A", version: 4, microphone: true };
  assert.equal(keepNewerPolicy(prior, other), other);
  assert.equal(keepNewerPolicy(prior, newer), newer);
});
