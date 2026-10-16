// Controlled async hook contracts; native-modal visibility is checked on the actual pin.
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const bundled = await build({ entryPoints: ["src/lib/use-folder-import.ts"], bundle: true, write: false, platform: "node", format: "esm",
  plugins: [{ name: "controlled-import-boundaries", setup(build) {
    build.onResolve({ filter: /^(react|\.\.\/api)$/ }, args => ({ path: args.path, namespace: "fixture" }));
    build.onLoad({ filter: /.*/, namespace: "fixture" }, args => ({ loader: "js", contents: args.path === "react"
      ? "export const useEffect=(...a)=>globalThis.__importHooks.useEffect(...a),useRef=(...a)=>globalThis.__importHooks.useRef(...a),useState=(...a)=>globalThis.__importHooks.useState(...a);"
      : "export const rpc=(...a)=>globalThis.__importRpc(...a);" }));
  }}] });
const { useFolderImport } = await import("data:text/javascript;base64," + Buffer.from(bundled.outputFiles[0].text).toString("base64"));
const P = "a".repeat(32), Q = "b".repeat(32);
const preview = { ticket: "reviewed-ticket", files: ["safe.txt"], bytes: 6 };
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
let restore;
afterEach(() => restore?.());
function harness(api) {
  const before = new Map(["__importHooks", "__importRpc"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  restore = () => { for (const [key, descriptor] of before) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } };
  const slots = [], imported = [], calls = [];
  let cursor = 0, dirty = false, queue = [], project = P, visible = true, view;
  globalThis.__importRpc = async (method, args) => { calls.push({ method, args }); return api(method, args); };
  globalThis.__importHooks = {
    useRef(value) { const index = cursor++; return slots[index] ?? (slots[index] = { current: value }); },
    useState(value) { const index = cursor++; slots[index] ??= { value }; return [slots[index].value, next => { slots[index].value = next; dirty = true; }]; },
    useEffect(effect, deps) { const index = cursor++, old = slots[index]; if (!old || deps.some((value, i) => !Object.is(value, old.deps[i]))) queue.push(() => { old?.cleanup?.(); slots[index] = { deps, cleanup: effect() }; }); },
  };
  function render(nextProject = project, nextVisible = visible) {
    project = nextProject; visible = nextVisible; cursor = 0; dirty = false; queue = [];
    view = useFolderImport(project, visible, files => imported.push(files));
    for (const effect of queue) effect();
    return view;
  }
  async function settle() { for (let i = 0; i < 5; i++) { await new Promise(resolve => setImmediate(resolve)); if (dirty) render(); } return view; }
  return { render, settle, calls, imported, unmount: () => { for (const slot of slots) slot.cleanup?.(); }, get view() { return view; } };
}
test("chooser failure stays in its dialog, retains the cause and clears immediately on retry", async () => {
  const retry = deferred(); let attempts = 0;
  const h = harness(() => ++attempts === 1 ? Promise.reject(Error("native_picker_unavailable")) : retry.promise);
  h.render(); await h.view.choose(); await h.settle();
  assert.match(h.view.error, /Could not choose.*native_picker_unavailable/);
  const pending = h.view.choose(); h.render();
  assert.equal(h.view.error, null); assert.equal(h.view.pending, "choosing");
  retry.resolve({ cancelled: true }); await pending; await h.settle();
  assert.equal(h.view.preview, null); assert.equal(h.view.error, null); assert.equal(h.view.pending, null);
});
test("an old chooser cannot repopulate a closed and reopened dialog or release its newer request", async () => {
  const old = deferred(), current = deferred(); let attempts = 0;
  const h = harness(() => ++attempts === 1 ? old.promise : current.promise);
  h.render(); const first = h.view.choose();
  h.render(P, false); h.render(P, true); const second = h.view.choose(); h.render();
  old.reject(Error("earlier denial")); await first; await h.settle();
  assert.equal(h.view.pending, "choosing"); assert.equal(h.view.error, null);
  current.resolve(preview); await second; await h.settle(); assert.deepEqual(h.view.preview, preview);
});
test("leaving and returning to a project rejects a late preview from its older opening", async () => {
  const pending = deferred(), h = harness(() => pending.promise);
  h.render(); const choose = h.view.choose(); h.render(Q); h.render(P);
  pending.resolve(preview); await choose; await h.settle();
  assert.equal(h.view.preview, null); assert.equal(h.view.pending, null);
});
test("changing project discards the reviewed ticket instead of committing it into the new project", async () => {
  const h = harness(() => preview); h.render(); await h.view.choose(); await h.settle();
  h.render(Q); await h.view.commit();
  assert.equal(h.calls.length, 1); assert.equal(h.view.preview, null);
});
test("copy retry preserves the reviewed ticket and successful completion opens only its captured project files", async () => {
  let attempts = 0;
  const h = harness((method, args) => {
    if (method === "workspace.import.request") return preview;
    assert.equal(args.project_id, P);
    if (method === "workspace.import.commit") { assert.equal(args.ticket, preview.ticket); if (++attempts === 1) throw Error("copy_admission_denied"); return {}; }
    assert.equal(method, "workspace.files"); return { files: ["safe.txt", "previous.txt"] };
  });
  h.render(); await h.view.choose(); await h.settle(); await h.view.commit(); await h.settle();
  assert.match(h.view.error, /copy_admission_denied/); assert.deepEqual(h.view.preview, preview);
  await h.view.commit(); await h.settle();
  assert.equal(h.view.error, null); assert.equal(h.view.preview, null);
  assert.deepEqual(h.imported, [["safe.txt", "previous.txt"]]);
});
test("a copy already sent remains bound to its original project and cannot open Files after a context change", async () => {
  const copy = deferred();
  const h = harness(method => method === "workspace.import.request" ? preview : copy.promise);
  h.render(); await h.view.choose(); await h.settle(); const committing = h.view.commit(); h.render(Q);
  copy.resolve({}); await committing; await h.settle();
  assert.deepEqual(h.calls[1], { method: "workspace.import.commit", args: { project_id: P, ticket: preview.ticket } });
  assert.equal(h.calls.length, 2); assert.deepEqual(h.imported, []); assert.equal(h.view.error, null);
});
test("a late file-list response cannot replace a newly reopened import dialog", async () => {
  const files = deferred();
  const h = harness(method => method === "workspace.import.request" ? preview : method === "workspace.files" ? files.promise : {});
  h.render(); await h.view.choose(); await h.settle(); const committing = h.view.commit(); await h.settle();
  h.render(P, false); h.render(P, true); files.resolve({ files: ["safe.txt"] }); await committing; await h.settle();
  assert.deepEqual(h.imported, []); assert.equal(h.view.preview, null);
});
test("a file-list failure reports that the copy happened and does not offer the spent ticket again", async () => {
  const h = harness(method => {
    if (method === "workspace.import.request") return preview;
    if (method === "workspace.files") throw Error("listing_unavailable"); return {};
  });
  h.render(); await h.view.choose(); await h.settle(); await h.view.commit(); await h.settle();
  assert.match(h.view.error, /Files were copied.*listing_unavailable/); assert.equal(h.view.preview, null);
  await h.view.commit(); assert.equal(h.calls.length, 3); assert.deepEqual(h.imported, []);
});
test("opening or cancelling a new import clears old review and error without another admission call", async () => {
  const h = harness(() => { throw Error("denied"); }); h.render(); await h.view.choose(); await h.settle();
  assert.ok(h.view.error); h.view.reset(); h.render();
  assert.equal(h.view.error, null); assert.equal(h.view.preview, null); assert.equal(h.calls.length, 1);
});
test("rapid repeated actions cannot create duplicate chooser or copy requests", async () => {
  const picker = deferred(), copy = deferred();
  const h = harness(method => method === "workspace.import.request" ? picker.promise : copy.promise);
  h.render(); const choosing = h.view.choose(); await h.view.choose(); assert.equal(h.calls.length, 1);
  picker.resolve(preview); await choosing; await h.settle();
  const copying = h.view.commit(); await h.view.commit(); assert.equal(h.calls.length, 2);
  h.render(P, false); copy.resolve({}); await copying;
});
test("no-project errors stay local and hidden or unmounted dialogs never publish late responses", async () => {
  const picker = deferred(), h = harness(() => picker.promise);
  h.render(null); await h.view.choose(); await h.settle(); assert.match(h.view.error, /select a project/); assert.equal(h.calls.length, 0);
  h.render(P, false); await h.view.choose(); assert.equal(h.calls.length, 0);
  h.render(P, true); const choosing = h.view.choose(); h.unmount(); picker.reject(Error("late denial")); await choosing;
  assert.deepEqual(h.imported, []);
});
