(function installHermesPerformanceProbe(options) {
  'use strict';
  options ??= {};
  if (location.origin !== 'http://127.0.0.1:18791' || location.pathname !== '/hermes-workspace') {
    throw new Error('actual_production_pin_required');
  }
  if (globalThis.__hermesPerformanceProbe?.active) throw new Error('performance_probe_already_active');
  const allowedOptions = new Set(['duration_ms', 'frame_limit', 'input_limit', 'longtask_limit']);
  if (Object.keys(options).some(key => !allowedOptions.has(key))) throw new Error('unknown_performance_option');
  function bounded(name, fallback, low, high) {
    const value = options[name] ?? fallback;
    if (!Number.isInteger(value) || value < low || value > high) throw new Error('bounded_performance_option_required');
    return value;
  }
  const limits = {
    duration_ms: bounded('duration_ms', 180000, 1000, 300000),
    frames: bounded('frame_limit', 50000, 1, 90000),
    inputs: bounded('input_limit', 2048, 1, 4096),
    longtasks: bounded('longtask_limit', 2048, 1, 4096),
    marks: 128,
    visibility: 128,
  };
  const started = performance.now();
  const data = {
    schema: 'hermes-cpu-performance-v1', limits,
    browser: {
      origin: location.origin, pathname: location.pathname,
      viewport_css: [innerWidth, innerHeight], dpr: devicePixelRatio,
      visual_viewport_scale: visualViewport?.scale ?? null,
      screen_css: [screen.width, screen.height], window_position_css: [screenX, screenY],
      reduced_motion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    },
    measurement: {
      frames: 'consecutive browser requestAnimationFrame timestamp intervals',
      inputs: 'trusted browser event timestamp and handler entry to next rAF callback entry; CPU feedback proxy',
      longtasks: 'PerformanceObserver longtask duration; not GPU execution',
      trusted_input_origin: 'browser isTrusted flag; does not distinguish physical from CDP input',
      phase_timing: 'explicit observer marks on this browser clock; may lag production state polling',
    },
    frames: [], inputs: [], longtasks: [], marks: [], visibility: [],
    ignored_untrusted_inputs: 0, longtask_status: 'unsupported',
    stop_reason: null, duration_ms: null,
  };
  let active = true;
  let previous = null;
  let pending = [];
  let frame = null;
  let timer = null;
  let observer = null;
  let visibilityRevision = 0;
  const now = () => performance.now() - started;
  const clone = () => JSON.parse(JSON.stringify(data));

  function collectLongtasks(entries) {
    for (const entry of entries) {
      if (entry.startTime < started) continue;
      if (data.longtasks.length === limits.longtasks) { stop('longtask_limit'); break; }
      data.longtasks.push({at_ms: entry.startTime - started, duration_ms: entry.duration});
    }
  }
  function stop(reason = 'caller') {
    if (active) {
      active = false;
      data.stop_reason = reason;
      data.duration_ms = now();
      if (frame !== null) cancelAnimationFrame(frame);
      if (timer !== null) clearTimeout(timer);
      for (const type of ['pointerdown', 'keydown', 'wheel', 'input']) removeEventListener(type, onInput, true);
      document.removeEventListener('visibilitychange', onVisibility);
      if (observer) {
        collectLongtasks(observer.takeRecords());
        observer.disconnect();
      }
      pending = [];
    }
    return clone();
  }
  function onVisibility() {
    if (!active) return;
    if (data.visibility.length === limits.visibility) { stop('visibility_limit'); return; }
    visibilityRevision += 1;
    data.visibility.push({at_ms: now(), hidden: document.hidden});
  }
  function onInput(event) {
    if (!active) return;
    if (!event.isTrusted) { data.ignored_untrusted_inputs += 1; return; }
    if (data.inputs.length === limits.inputs) { stop('input_limit'); return; }
    const absolute = performance.now();
    const usable = Number.isFinite(event.timeStamp) && event.timeStamp >= 0 && event.timeStamp <= absolute
      && absolute - event.timeStamp <= limits.duration_ms;
    // No key, text, target, title or conversation content is collected.
    const row = {type: event.type, at_ms: absolute - started, hidden_at_handler: document.hidden,
      event_to_handler_ms: usable ? absolute - event.timeStamp : null,
      handler_to_next_raf_ms: null, event_to_next_raf_ms: null,
      callback_at_ms: null, hidden_at_callback: null};
    data.inputs.push(row);
    pending.push(row);
  }
  function onFrame(timestamp) {
    if (!active) return;
    const absolute = performance.now();
    const at = absolute - started;
    if (previous) {
      if (data.frames.length === limits.frames) { stop('frame_limit'); return; }
      data.frames.push({from_ms: previous.at, to_ms: at, interval_ms: timestamp - previous.timestamp,
        visible_entire_interval: !previous.hidden && !document.hidden && previous.revision === visibilityRevision});
    }
    for (const row of pending) {
      row.callback_at_ms = at;
      row.hidden_at_callback = document.hidden;
      row.handler_to_next_raf_ms = at - row.at_ms;
      row.event_to_next_raf_ms = row.event_to_handler_ms === null ? null
        : row.event_to_handler_ms + row.handler_to_next_raf_ms;
    }
    pending = [];
    previous = {at, timestamp, hidden: document.hidden, revision: visibilityRevision};
    frame = requestAnimationFrame(onFrame);
  }
  function mark(fields) {
    if (!active) throw new Error('performance_probe_stopped');
    const phases = new Set(['idle', 'ui_interaction', 'queued', 'searching', 'admitting', 'generating',
      'streaming', 'cancelling', 'restoring', 'completed', 'failed', 'cancelled']);
    const bases = new Set(['idle_observation', 'production_rpc_state', 'production_stream_delta', 'trusted_UI_action']);
    if (!fields || Object.keys(fields).sort().join(',') !== 'arm,basis,phase,run_id'
        || !['none', 'normal', 'abliterated'].includes(fields.arm) || !phases.has(fields.phase)
        || !bases.has(fields.basis) || !(fields.run_id === null || (typeof fields.run_id === 'string' && /^[0-9a-f]{32}$/.test(fields.run_id)))) {
      throw new Error('explicit_bounded_performance_mark_required');
    }
    if (data.marks.length === limits.marks) { stop('mark_limit'); throw new Error('performance_mark_limit'); }
    data.marks.push({at_ms: now(), ...fields});
    return data.marks.length - 1;
  }
  data.visibility.push({at_ms: 0, hidden: document.hidden});
  if (typeof PerformanceObserver === 'function' && PerformanceObserver.supportedEntryTypes?.includes('longtask')) {
    try {
      observer = new PerformanceObserver(list => { if (active) collectLongtasks(list.getEntries()); });
      observer.observe({type: 'longtask', buffered: false});
      data.longtask_status = 'observing';
    } catch {
      observer?.disconnect();
      observer = null;
      data.longtask_status = 'observation_failed';
    }
  }
  for (const type of ['pointerdown', 'keydown', 'wheel', 'input']) addEventListener(type, onInput, {capture: true, passive: true});
  document.addEventListener('visibilitychange', onVisibility);
  frame = requestAnimationFrame(onFrame);
  timer = setTimeout(() => stop('duration_limit'), limits.duration_ms);
  globalThis.__hermesPerformanceProbe = Object.freeze({mark, stop,
    snapshot: () => ({...clone(), active, elapsed_ms: now()}), get active() { return active; }});
  return {schema: data.schema, active, limits};
})
