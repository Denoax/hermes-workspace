// Real Recorder lifecycle with controlled authorization and fake device tracks; no ambient microphone/device access.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
const built = await build({
  stdin: {
    contents:
      'export {RecordingSession} from "./src/recording-session"; export {Recorder} from "./src/recording";',
    resolveDir: process.cwd(),
    loader: "ts",
  },
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { RecordingSession, Recorder } = await import(
  "data:text/javascript;base64," +
    Buffer.from(built.outputFiles[0].text).toString("base64")
);
let original, calls, stopped, grants;
const deferred = () => {
  let resolve;
  return {
    promise: new Promise((r) => (resolve = r)),
    resolve: (value) => resolve(value),
  };
};
beforeEach(() => {
  original = new Map(
    ["navigator", "MediaRecorder"].map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  calls = 0;
  stopped = 0;
  grants = [];
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia() {
          calls++;
          const grant = deferred();
          grants.push(grant);
          return grant.promise;
        },
      },
    },
  });
  globalThis.MediaRecorder = class {
    static isTypeSupported() {
      return true;
    }
    constructor() {
      this.state = "inactive";
      this.mimeType = "audio/webm";
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
    }
  };
});
afterEach(() => {
  for (const [key, descriptor] of original) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});
const tracks = () => ({
  getTracks: () => [
    {
      stop() {
        stopped++;
      },
    },
  ],
});
const tick = () => new Promise((resolve) => setImmediate(resolve));
test("authorization A followed by navigation B cannot request GUM when the old allow arrives", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder),
    auth = deferred();
  let selected = "A";
  const started = capture.start(
    "A",
    () => auth.promise,
    () => selected === "A",
    [],
  );
  const rejected = assert.rejects(started, { name: "AbortError" });
  selected = "B";
  assert.equal(capture.reconcile("B", false), "conversation");
  auth.resolve();
  await rejected;
  assert.equal(calls, 0);
  assert.equal(recorder.tracks, null);
});
test("GUM A followed by navigation B releases every track from a late browser grant", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder);
  let selected = "A";
  const started = capture.start(
    "A",
    async () => {},
    () => selected === "A",
    [],
  );
  const rejected = assert.rejects(started, { name: "AbortError" });
  await tick();
  assert.equal(calls, 1);
  selected = "B";
  capture.reconcile("B", false);
  grants[0].resolve(tracks());
  await rejected;
  assert.equal(stopped, 1);
  assert.equal(recorder.tracks, null);
  assert.equal(recorder.media, null);
});
test("microphone revocation invalidates a pending grant and releases it on arrival", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder);
  const started = capture.start(
    "A",
    async () => {},
    () => true,
    [],
  );
  const rejected = assert.rejects(started, { name: "AbortError" });
  await tick();
  assert.equal(capture.reconcile("A", false), "permission");
  grants[0].resolve(tracks());
  await rejected;
  assert.equal(stopped, 1);
  assert.equal(recorder.tracks, null);
});
test("unmount-style cancellation invalidates a pending grant and releases it on arrival", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder);
  const started = capture.start(
    "A",
    async () => {},
    () => true,
    [],
  );
  const rejected = assert.rejects(started, { name: "AbortError" });
  await tick();
  capture.cancel();
  grants[0].resolve(tracks());
  await rejected;
  assert.equal(stopped, 1);
  assert.equal(recorder.media, null);
});
test("an older authorization cannot cancel a newer capture owner; revocation still releases the new active capture", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder),
    oldAuth = deferred();
  let selected = "A";
  const old = capture.start(
    "A",
    () => oldAuth.promise,
    () => selected === "A",
    [],
  );
  const rejected = assert.rejects(old, { name: "AbortError" });
  selected = "B";
  const current = capture.start(
    "B",
    async () => {},
    () => selected === "B",
    [],
  );
  await tick();
  grants[0].resolve(tracks());
  await current;
  oldAuth.resolve();
  await rejected;
  assert.equal(recorder.media.state, "recording");
  assert.equal(stopped, 0);
  capture.reconcile("B", false);
  assert.equal(stopped, 1);
  assert.equal(recorder.media, null);
});
test("conversation cancellation settles a pending stop even when the recorder's native stop event is late", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder);
  const started = capture.start(
    "A",
    async () => {},
    () => true,
    [],
  );
  await tick();
  grants[0].resolve(tracks());
  await started;
  const stopping = capture.stop(),
    rejected = assert.rejects(stopping, { name: "AbortError" });
  capture.reconcile("B", false);
  await rejected;
  assert.equal(stopped, 1);
  assert.equal(recorder.media, null);
});
test("a lifecycle check after GUM also releases a grant when visibility changed without a prior event", async () => {
  const recorder = new Recorder(),
    capture = new RecordingSession(recorder);
  let visible = true;
  const started = capture.start(
    "A",
    async () => {},
    () => visible,
    [],
  );
  const rejected = assert.rejects(started, { name: "AbortError" });
  await tick();
  visible = false;
  grants[0].resolve(tracks());
  await rejected;
  assert.equal(stopped, 1);
  assert.equal(recorder.media, null);
});
function readyPort() {
  return {
    start: async () => {},
    cancel() {},
    stop: async () => new Blob(["owned recording"]),
  };
}
for (const mode of ["navigation", "roundtrip", "revocation", "unmount"]) {
  test(`late voice preparation after ${mode} cannot publish its result`, async () => {
    const capture = new RecordingSession(readyPort()),
      preparation = deferred(),
      entered = deferred();
    let selected = "A",
      published = false,
      finished = false;
    await capture.start(
      "A",
      async () => {},
      () => selected === "A",
      [],
    );
    const stopping = capture.stop(async (blob) => {
      entered.resolve();
      await preparation.promise;
      finished = true;
      return { blob, measured: "actual preparation" };
    });
    const rejected = assert.rejects(
      stopping.then((value) => {
        published = true;
        return value;
      }),
      { name: "AbortError" },
    );
    await entered.promise;
    if (mode === "navigation" || mode === "roundtrip") {
      selected = "B";
      capture.reconcile("B", true);
      if (mode === "roundtrip") {
        selected = "A";
        capture.reconcile("A", true);
      }
    } else if (mode === "revocation") capture.reconcile("A", false);
    else capture.cancel();
    await rejected;
    preparation.resolve();
    await tick();
    assert.equal(finished, true);
    assert.equal(published, false);
  });
}
test("successful voice preparation returns its result before retiring the original owner", async () => {
  const capture = new RecordingSession(readyPort()),
    preparation = deferred(),
    entered = deferred();
  await capture.start(
    "A",
    async () => {},
    () => true,
    [],
  );
  const stopping = capture.stop(async (blob) => {
    entered.resolve();
    await preparation.promise;
    return { blob, measured: { duration: 1 } };
  });
  await entered.promise;
  preparation.resolve();
  const result = await stopping;
  assert.equal(result.measured.duration, 1);
  assert.equal(await result.blob.text(), "owned recording");
  assert.equal(capture.reconcile("B", false), null);
});
test("the stored selected predicate is checked again when preparation resolves even without a lifecycle event", async () => {
  const capture = new RecordingSession(readyPort()),
    preparation = deferred(),
    entered = deferred();
  let selected = true;
  await capture.start(
    "A",
    async () => {},
    () => selected,
    [],
  );
  const stopping = capture.stop(async (blob) => {
    entered.resolve();
    await preparation.promise;
    return blob;
  });
  const rejected = assert.rejects(stopping, { name: "AbortError" });
  await entered.promise;
  selected = false;
  preparation.resolve();
  await rejected;
});
