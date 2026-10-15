import { test } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/api.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const source = built.outputFiles[0].text;
const fresh = () =>
  import(
    "data:text/javascript;base64," +
      Buffer.from(source + "\n//" + crypto.randomUUID()).toString("base64")
  );
const original = globalThis.fetch;
test("concurrent startup RPCs wait for one CSRF bootstrap", async () => {
  const calls = [];
  let release;
  const ready = new Promise((resolve) => (release = resolve));
  globalThis.fetch = async (url, options) => {
    calls.push(url);
    if (url.endsWith("/bootstrap")) {
      await ready;
      return Response.json({ csrf: "test-token", version: 1 });
    }
    assert.equal(options.headers["X-Hermes-CSRF"], "test-token");
    return Response.json({ result: "ok" });
  };
  try {
    const api = await fresh();
    const pending = [api.rpc("permissions.read"), api.rpc("view.read")];
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(calls.length, 1);
    release();
    assert.deepEqual(await Promise.all(pending), ["ok", "ok"]);
    assert.equal(calls.filter((url) => url.endsWith("/bootstrap")).length, 1);
  } finally {
    globalThis.fetch = original;
  }
});
test("a rotated CSRF token refreshes once and preserves the operation body", async () => {
  let boot = 0;
  const bodies = [];
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/bootstrap"))
      return Response.json({ csrf: "token-" + ++boot, version: 1 });
    bodies.push(options.body);
    return options.headers["X-Hermes-CSRF"] === "token-1"
      ? Response.json({ error: "session_or_CSRF_denied" }, { status: 403 })
      : Response.json({ result: "accepted" });
  };
  try {
    const api = await fresh();
    assert.equal(
      await api.rpc("chat.submit", { request_id: "same-request" }),
      "accepted",
    );
    assert.equal(boot, 2);
    assert.equal(bodies.length, 2);
    assert.equal(bodies[0], bodies[1]);
  } finally {
    globalThis.fetch = original;
  }
});
test("an application permission denial is never replayed", async () => {
  let attempts = 0;
  globalThis.fetch = async (url) =>
    url.endsWith("/bootstrap")
      ? Response.json({ csrf: "token", version: 1 })
      : (attempts++,
        Response.json({ error: "permission_denied" }, { status: 403 }));
  try {
    const api = await fresh();
    await assert.rejects(api.rpc("actions.execute"), /permission_denied/);
    assert.equal(attempts, 1);
  } finally {
    globalThis.fetch = original;
  }
});
