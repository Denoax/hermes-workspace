// Labelled MediaRecorder/device fixtures. No physical microphone evidence.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";

const result = await build({
  entryPoints: ["src/recording.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { Recorder, waveform } = await import(
  "data:text/javascript;base64," +
    Buffer.from(result.outputFiles[0].text).toString("base64")
);
let stopped, media, deadline, timerCleared;
const saved = Object.fromEntries(
  [
    "navigator",
    "MediaRecorder",
    "AudioContext",
    "setTimeout",
    "clearTimeout",
    "requestAnimationFrame",
    "cancelAnimationFrame",
  ].map((k) => [k, Object.getOwnPropertyDescriptor(globalThis, k)]),
);
beforeEach(() => {
  stopped = 0;
  media = null;
  deadline = null;
  timerCleared = false;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async () => ({
          getTracks: () => [{ stop: () => stopped++ }],
        }),
      },
    },
  });
  globalThis.MediaRecorder = class {
    static isTypeSupported(type) {
      return type.startsWith("audio/webm");
    }
    constructor() {
      media = this;
      this.mimeType = "audio/webm;codecs=opus";
      this.state = "inactive";
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      queueMicrotask(() => this.onstop?.());
    }
  };
  globalThis.setTimeout = (fn) => {
    deadline = fn;
    return 42;
  };
  globalThis.clearTimeout = () => {
    timerCleared = true;
  };
});
afterEach(() => {
  for (const [key, descriptor] of Object.entries(saved)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

for (const name of ["NotAllowedError", "NotFoundError"])
  test(name + " leaves no recorder or device owner", async () => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("labelled device fixture", name);
    };
    const r = new Recorder();
    await assert.rejects(r.start(), { name });
    assert.equal(r.tracks, null);
    assert.equal(r.media, null);
  });
test("constructor failure releases acquired tracks", async () => {
  globalThis.MediaRecorder = class {
    static isTypeSupported() {
      return true;
    }
    constructor() {
      throw Error("fixture codec failure");
    }
  };
  const r = new Recorder();
  await assert.rejects(r.start(), /codec failure/);
  assert.equal(stopped, 1);
  assert.equal(r.tracks, null);
});
test("stop returns captured bytes and releases the microphone and limit timer", async () => {
  const r = new Recorder();
  await r.start();
  media.ondataavailable({ data: new Blob(["labelled fixture bytes"]) });
  const blob = await r.stop();
  assert.equal(await blob.text(), "labelled fixture bytes");
  assert.equal(stopped, 1);
  assert.equal(timerCleared, true);
  assert.equal(r.media, null);
});
test("cancel discards chunks and releases tracks", async () => {
  const r = new Recorder();
  await r.start();
  media.ondataavailable({ data: new Blob(["not sent"]) });
  r.cancel();
  assert.equal(stopped, 1);
  assert.equal(r.chunks.length, 0);
  assert.equal(r.tracks, null);
  assert.equal(timerCleared, true);
});
test("absolute recording limit cancels the owned capture", async () => {
  const r = new Recorder();
  let limited = false;
  await r.start(() => {
    limited = true;
  });
  deadline();
  assert.equal(stopped, 1);
  assert.equal(limited, true);
  assert.equal(r.media, null);
});
test("decode failure closes its AudioContext", async () => {
  let closed = false;
  globalThis.AudioContext = class {
    async decodeAudioData() {
      throw Error("fixture decode failure");
    }
    async close() {
      closed = true;
    }
  };
  await assert.rejects(
    waveform(new Blob(["inert invalid audio"])),
    /decode failure/,
  );
  assert.equal(closed, true);
});

test("live meter reads acquired samples and releases its graph on cancellation", async () => {
  let measure,
    cancelled = false,
    closed = false,
    disconnected = false,
    levels;
  globalThis.requestAnimationFrame = (callback) => {
    measure = callback;
    return 7;
  };
  globalThis.cancelAnimationFrame = (id) => {
    cancelled = id === 7;
  };
  globalThis.AudioContext = class {
    createMediaStreamSource() {
      return {
        connect() {},
        disconnect() {
          disconnected = true;
        },
      };
    }
    createAnalyser() {
      return {
        fftSize: 1024,
        getFloatTimeDomainData(samples) {
          samples.fill(0.25);
        },
      };
    }
    async close() {
      closed = true;
    }
  };
  const recorder = new Recorder();
  await recorder.start(undefined, (values) => {
    levels = values;
  });
  measure(100);
  assert.deepEqual(levels, Array(32).fill(0.25));
  recorder.cancel();
  assert.equal(stopped, 1);
  assert.equal(cancelled, true);
  assert.equal(closed, true);
  assert.equal(disconnected, true);
});
test("meter startup failure stops the recorder and acquired tracks", async () => {
  globalThis.AudioContext = class {
    constructor() {
      throw Error("fixture meter failure");
    }
  };
  const recorder = new Recorder();
  await assert.rejects(
    recorder.start(undefined, () => {}),
    /meter failure/,
  );
  assert.equal(stopped, 1);
  assert.equal(media.state, "inactive");
  assert.equal(recorder.media, null);
});
test("cancel while browser permission is pending releases a late device grant", async () => {
  let grant;
  const pending = new Promise((resolve) => (grant = resolve));
  navigator.mediaDevices.getUserMedia = () => pending;
  const r = new Recorder();
  const starting = r.start();
  r.cancel();
  grant({ getTracks: () => [{ stop: () => stopped++ }] });
  await assert.rejects(starting, { name: "AbortError" });
  assert.equal(stopped, 1);
  assert.equal(r.tracks, null);
  assert.equal(r.media, null);
});
test("device loss retires recording, callbacks and all acquired tracks", async () => {
  const track = new EventTarget();
  track.stop = () => stopped++;
  navigator.mediaDevices.getUserMedia = async () => ({
    getTracks: () => [track],
  });
  const r = new Recorder();
  let lost = 0;
  await r.start(undefined, undefined, () => lost++);
  track.dispatchEvent(new Event("ended"));
  assert.equal(lost, 1);
  assert.equal(stopped, 1);
  assert.equal(r.tracks, null);
  assert.equal(r.media, null);
  track.dispatchEvent(new Event("ended"));
  assert.equal(lost, 1);
});
