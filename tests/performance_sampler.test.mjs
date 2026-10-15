import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../scripts/performance_sampler.js', import.meta.url), 'utf8');
function browser(options = {}, origin = 'http://127.0.0.1:18791', supported = true) {
  let clock = 0;
  let next = 1;
  const frames = new Map();
  const timers = new Map();
  const listeners = new Map();
  const queue = [];
  let observer;
  const document = {hidden: false,
    addEventListener: (type, call) => listeners.set(type, call),
    removeEventListener: type => listeners.delete(type)};
  class Observer {
    static supportedEntryTypes = supported ? ['longtask'] : [];
    constructor(call) { this.call = call; this.disconnected = false; observer = this; }
    observe() {}
    takeRecords() { return queue.splice(0); }
    disconnect() { this.disconnected = true; }
  }
  const environment = {location: {origin, pathname: '/hermes-workspace'}, document,
    innerWidth: 1280, innerHeight: 720, devicePixelRatio: 1.25, visualViewport: {scale: 1},
    screen: {width: 1920, height: 1080}, screenX: 0, screenY: 0,
    matchMedia: () => ({matches: false}), performance: {now: () => clock},
    PerformanceObserver: Observer,
    requestAnimationFrame: call => {const id = next++; frames.set(id, call); return id;},
    cancelAnimationFrame: id => frames.delete(id),
    setTimeout: call => {const id = next++; timers.set(id, call); return id;},
    clearTimeout: id => timers.delete(id),
    addEventListener: (type, call) => listeners.set(type, call),
    removeEventListener: type => listeners.delete(type)};
  const context = vm.createContext(environment);
  const install = vm.runInContext(source, context);
  const installResult = install(options);
  const probe = context.__hermesPerformanceProbe;
  return {probe, installResult, listeners, frames, timers, queue,
    at: value => {clock = value;},
    frame: value => {clock = value; const calls = [...frames.values()]; frames.clear(); calls.forEach(call => call(value));},
    input: (type, values = {}) => listeners.get(type)?.({type, isTrusted: true, timeStamp: clock, ...values}),
    hidden: (hidden, at) => {clock = at; document.hidden = hidden; listeners.get('visibilitychange')?.();},
    tasks: rows => observer.call({getEntries: () => rows}),
    plain: value => JSON.parse(JSON.stringify(value))};
}
const mark = {arm: 'normal', phase: 'generating', run_id: 'a'.repeat(32), basis: 'production_rpc_state'};

test('only the actual production origin and path can be sampled', () => {
  assert.throws(() => browser({}, 'http://127.0.0.1:18888'), /actual_production_pin_required/);
});

test('trusted event timestamp and handler delay retain the adverse next callback', () => {
  const b = browser();
  b.probe.mark(mark);
  b.frame(10);
  b.at(15);
  b.input('keydown', {timeStamp: 8, key: 'PRIVATE', target: {value: 'PRIVATE'}});
  b.frame(115);
  const raw = b.probe.stop();
  assert.equal(raw.frames[0].interval_ms, 105);
  assert.equal(raw.inputs[0].handler_to_next_raf_ms, 100);
  assert.equal(raw.inputs[0].event_to_next_raf_ms, 107);
  assert.equal(raw.inputs[0].event_to_handler_ms, 7);
  assert.equal(JSON.stringify(raw).includes('PRIVATE'), false);
  b.tasks([{startTime: 20, duration: 80}]);
  assert.equal(b.probe.snapshot().longtasks.length, 0);
});

test('hidden intervals remain in raw data and are identified for honest summaries', () => {
  const b = browser();
  b.frame(10);
  b.hidden(true, 11);
  b.hidden(false, 1000);
  b.frame(1010);
  b.frame(1020);
  const raw = b.probe.stop();
  assert.equal(raw.frames[0].interval_ms, 1000);
  assert.equal(raw.frames[0].visible_entire_interval, false);
  assert.equal(raw.frames[1].visible_entire_interval, true);
  assert.equal(raw.visibility.length, 3);
});

test('untrusted events are counted separately and never promoted into input samples', () => {
  const b = browser();
  b.input('pointerdown', {isTrusted: false});
  b.input('input', {timeStamp: -10});
  b.frame(10);
  const raw = b.probe.stop();
  assert.equal(raw.ignored_untrusted_inputs, 1);
  assert.equal(raw.inputs.length, 1);
  assert.equal(raw.inputs[0].event_to_next_raf_ms, null);
  assert.equal(raw.inputs[0].handler_to_next_raf_ms, 10);
});

test('bounded collection stops with raw adverse samples and removes all listeners', () => {
  const b = browser({frame_limit: 1});
  b.frame(10); b.frame(110); b.frame(120);
  const raw = b.probe.snapshot();
  assert.equal(raw.active, false);
  assert.equal(raw.stop_reason, 'frame_limit');
  assert.equal(raw.frames.length, 1);
  assert.equal(raw.frames[0].interval_ms, 100);
  assert.equal(b.listeners.size, 0);
  assert.equal(b.frames.size, 0);
  assert.equal(b.timers.size, 0);
});

test('stop retains input without a later rAF as incomplete and flushes pending longtasks', () => {
  const b = browser();
  b.at(10); b.input('wheel');
  b.queue.push({startTime: 5, duration: 90, name: 'PRIVATE'});
  const raw = b.probe.stop();
  assert.equal(raw.inputs[0].callback_at_ms, null);
  assert.deepEqual(b.plain(raw.longtasks), [{at_ms: 5, duration_ms: 90}]);
  assert.equal(JSON.stringify(raw).includes('PRIVATE'), false);
});

test('phase marks require explicit observed basis and bounded run identity', () => {
  const b = browser();
  assert.throws(() => b.probe.mark({...mark, basis: 'guessed'}), /explicit_bounded/);
  assert.throws(() => b.probe.mark({...mark, run_id: 'PRIVATE'}), /explicit_bounded/);
  assert.throws(() => b.probe.mark({...mark, run_id: {toString: () => 'a'.repeat(32)}}), /explicit_bounded/);
  assert.throws(() => b.probe.mark({...mark, prompt: 'PRIVATE'}), /explicit_bounded/);
  b.probe.mark(mark);
  b.at(30); b.probe.mark({...mark, phase: 'streaming', basis: 'production_stream_delta'});
  assert.equal(b.probe.stop().marks[1].at_ms, 30);
});

test('missing longtask support is explicit and duration completion remains bounded', () => {
  const b = browser({}, 'http://127.0.0.1:18791', false);
  b.at(180000); [...b.timers.values()][0]();
  const raw = b.probe.stop();
  assert.equal(raw.stop_reason, 'duration_limit');
  assert.equal(raw.longtask_status, 'unsupported');
  assert.equal(raw.duration_ms, 180000);
});
