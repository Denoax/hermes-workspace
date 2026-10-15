// Controlled hook/effect lifecycle fixture; actual rendered retention is checked separately on the production pin.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  entryPoints: ["src/lib/use-draft-attachments.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
  plugins: [
    {
      name: "controlled-boundaries",
      setup(build) {
        build.onResolve({ filter: /^(react|\.\.\/api)$/ }, (args) => ({
          path: args.path,
          namespace: "fixture",
        }));
        build.onLoad({ filter: /.*/, namespace: "fixture" }, (args) => ({
          contents:
            args.path === "react"
              ? "export const useEffect=(...args)=>globalThis.__draftHooks.useEffect(...args),useRef=(...args)=>globalThis.__draftHooks.useRef(...args),useState=(...args)=>globalThis.__draftHooks.useState(...args);"
              : "export const rpc=(...args)=>globalThis.__draftRpc(...args);",
          loader: "js",
        }));
      },
    },
  ],
});
const { useDraftAttachments } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
const a = "a".repeat(32),
  b = "b".repeat(32),
  c = "c".repeat(32),
  d = "d".repeat(32);
const key = (scope) => "hermes:draft-attachments:v1:" + (scope ?? "new");
const item = (id) => ({
  id,
  name: "fixture.txt",
  mime: "text/plain",
  metadata: {},
});
let restoreGlobals;
afterEach(() => restoreGlobals?.());
function harness(initial, metadata = async (id) => item(id)) {
  const previous = new Map(
    [
      "localStorage",
      "addEventListener",
      "removeEventListener",
      "__draftHooks",
      "__draftRpc",
    ].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
  );
  restoreGlobals = () => {
    for (const [key, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  };
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.__draftRpc = async (method, { id }) => {
    assert.equal(method, "attachment.metadata");
    return metadata(id);
  };
  let scope = initial,
    cursor = 0,
    dirty = false,
    view,
    queue = [];
  const slots = [];
  globalThis.__draftHooks = {
    useRef(value) {
      const index = cursor++;
      return slots[index] ?? (slots[index] = { current: value });
    },
    useState(value) {
      const index = cursor++;
      if (!slots[index])
        slots[index] = { value: typeof value === "function" ? value() : value };
      return [
        slots[index].value,
        (next) => {
          slots[index].value =
            typeof next === "function" ? next(slots[index].value) : next;
          dirty = true;
        },
      ];
    },
    useEffect(effect, deps) {
      const index = cursor++,
        before = slots[index];
      if (!before || deps.some((dep, i) => !Object.is(dep, before.deps[i])))
        queue.push(() => {
          before?.cleanup?.();
          slots[index] = { deps, cleanup: effect() };
        });
    },
  };
  function render(next = scope) {
    scope = next;
    cursor = 0;
    queue = [];
    dirty = false;
    view = useDraftAttachments(scope, true);
    for (const effect of queue) effect();
    return view;
  }
  async function settle() {
    for (let i = 0; i < 8; i++) {
      await new Promise((resolve) => setImmediate(resolve));
      if (dirty) render();
    }
    return view;
  }
  function save(scope, ids) {
    values.set(
      key(scope),
      JSON.stringify({
        version: 1,
        revision: crypto.randomUUID().replaceAll("-", ""),
        ids,
      }),
    );
  }
  return {
    render,
    settle,
    save,
    get view() {
      return view;
    },
    ids: (scope) => JSON.parse(values.get(key(scope)) ?? '{"ids":[]}').ids,
  };
}
test("late metadata from an old conversation cannot replace the new conversation's view", async () => {
  let release;
  const blocked = new Promise((resolve) => (release = resolve));
  const h = harness(c, async (id) => {
    if (id === a) await blocked;
    return item(id);
  });
  h.save(c, [a]);
  h.save(d, [b]);
  h.render();
  h.render(d);
  await h.settle();
  assert.deepEqual(
    h.view.items.map((row) => row.id),
    [b],
  );
  release();
  await h.settle();
  assert.deepEqual(
    h.view.items.map((row) => row.id),
    [b],
  );
  assert.equal(h.view.ready, true);
});
test("a late upload is saved only in its captured conversation and reported as background", async () => {
  const h = harness(c);
  h.save(c, []);
  h.save(d, [b]);
  h.render();
  await h.settle();
  const token = h.view.capture();
  h.render(d);
  await h.settle();
  const added = h.view.add(item(a), token);
  await h.settle();
  assert.equal(added.background, true);
  assert.deepEqual(h.ids(c), [a]);
  assert.deepEqual(h.ids(d), [b]);
  assert.deepEqual(
    h.view.items.map((row) => row.id),
    [b],
  );
});
test("accepted submission cannot clear a follow-up attachment added after its token was captured", async () => {
  const h = harness(c);
  h.save(c, [a]);
  h.render();
  await h.settle();
  const submitted = h.view.capture();
  h.view.add(item(b), submitted);
  await h.settle();
  assert.equal(h.view.clearAccepted(submitted), null);
  assert.deepEqual(h.ids(c), [a, b]);
  assert.deepEqual(
    h.view.items.map((row) => row.id),
    [a, b],
  );
});
test("missing metadata keeps a removable issue and retry can restore the actual metadata", async () => {
  let available = false;
  const h = harness(c, async (id) => {
    if (!available) throw Error("gone");
    return item(id);
  });
  h.save(c, [a]);
  h.render();
  await h.settle();
  assert.deepEqual(
    h.view.issues.map((issue) => issue.id),
    [a],
  );
  assert.throws(() => h.view.capture(), /Resolve unavailable/);
  available = true;
  h.view.retry();
  await h.settle();
  assert.deepEqual(
    h.view.items.map((row) => row.id),
    [a],
  );
  assert.deepEqual(h.view.issues, []);
});
