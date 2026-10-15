// Application port of Mani's GooeyNav and navConnection at bab9d618.
// Copyright (c) 2026 Swami Malode / Rare UI. Notices in licenses/.
const smooth = value => { const x = Math.max(0, Math.min(1, value)); return x * x * (3 - 2 * x); };
export function navConnection(gap, height, radius, span) {
  if (![gap, height, radius, span].every(Number.isFinite) || height <= 0 || span <= 0) return { path: '', corner: Math.max(0, radius || 0), coverage: 0 };
  const r = Math.max(0, Math.min(radius, height / 2));
  const coverage = 1 - smooth(Math.max(0, gap) / (span * .22));
  const corner = r * smooth(gap + 1);
  if (coverage === 0) return { path: '', corner, coverage };
  const overlap = r * coverage + .35 * coverage;
  const left = -gap - overlap, right = overlap, middle = -gap / 2;
  const top = height * .5 * (1 - coverage), pinch = height * .5 * (1 - coverage * coverage), control = (right - left) * .2;
  const path = `M${left} ${top} C${left + control} ${top} ${middle - control} ${pinch} ${middle} ${pinch} C${middle + control} ${pinch} ${right - control} ${top} ${right} ${top} L${right} ${height - top} C${right - control} ${height - top} ${middle + control} ${height - pinch} ${middle} ${height - pinch} C${middle - control} ${height - pinch} ${left + control} ${height - top} ${left} ${height - top} Z`;
  return { path, corner, coverage };
}
// Exact 200/28/1 damped spring solution, preserving current velocity on retarget.
export function springStep(value, velocity, target, dt) {
  const time = Math.max(0, Math.min(.05, dt)), x = value - target;
  const decay = Math.exp(-14 * time), c = Math.cos(2 * time), s = Math.sin(2 * time), b = (velocity + 14 * x) / 2;
  return { value: target + decay * (x * c + b * s), velocity: decay * ((-14 * x + 2 * b) * c + (-14 * b - 2 * x) * s) };
}
export function navGapTarget(index, selected) { return index === 0 ? 0 : index === selected || index - 1 === selected ? 20 : -1; }
export function installPortfolioNav() {
  const items = [...document.querySelectorAll('.portfolio-nav .gooey-segment')];
  const gaps = items.map((_, i) => ({ value: i ? -1 : 0, velocity: 0 }));
  let selected = -1, frame = 0, stamp = 0;
  const reduced = () => document.documentElement.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const target = i => navGapTarget(i, selected);
  // Reserve the two source seams, so right-aligned toolbar layout cannot
  // cancel the active Settings segment's actual 20px movement.
  const reserve = () => { const width=items.reduce((sum,item)=>sum+item.offsetWidth,0)+40; document.querySelector('.portfolio-nav').style.setProperty('--nav-reserved',width+'px'); };
  const observer = new ResizeObserver(reserve);items.forEach(item=>observer.observe(item));reserve();
  function paint() {
    items.forEach((item, i) => {
      const active = i === selected, left = navConnection(gaps[i].value, 40, 12, 20), right = gaps[i + 1] && navConnection(gaps[i + 1].value, 40, 12, 20);
      item.style.marginLeft = gaps[i].value + 'px';
      item.style.borderTopLeftRadius = item.style.borderBottomLeftRadius = (i ? left.corner : 12) + 'px';
      item.style.borderTopRightRadius = item.style.borderBottomRightRadius = (right ? right.corner : 12) + 'px';
      item.dataset.active = String(active); if(item.querySelector('button').hasAttribute('aria-controls'))item.querySelector('button').setAttribute('aria-expanded', String(active));
      if (i) {
        const path = item.querySelector('.gooey-neck path'); path.setAttribute('d', left.path);
        const stops = item.querySelectorAll('.gooey-neck stop');
        stops[0].setAttribute('stop-color', i - 1 === selected ? 'var(--nav-selected)' : 'var(--nav-body)');
        stops[1].setAttribute('stop-color', active ? 'var(--nav-selected)' : 'var(--nav-body)');
      }
    });
  }
  function tick(now) {
    const dt = stamp ? (now - stamp) / 1000 : 1 / 60; stamp = now;
    let moving = false;
    gaps.forEach((gap, i) => {
      const end = target(i), next = reduced() ? { value: end, velocity: 0 } : springStep(gap.value, gap.velocity, end, dt);
      Object.assign(gap, next);
      if (Math.abs(gap.value - end) < .005 && Math.abs(gap.velocity) < .03) { gap.value = end; gap.velocity = 0; } else moving = true;
    });
    paint(); frame = moving && !document.hidden ? requestAnimationFrame(tick) : 0;
  }
  items.forEach((item, i) => {
    if (!i) return;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '-34 0 48 40'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('class', 'gooey-neck');
    const ns = 'http://www.w3.org/2000/svg';
    const defs = document.createElementNS(ns, 'defs'), gradient = document.createElementNS(ns, 'linearGradient');
    gradient.id = 'hermes-nav-bridge-' + i; gradient.setAttribute('x1', '0'); gradient.setAttribute('x2', '1');
    for (const offset of ['0','1']) { const stop = document.createElementNS(ns, 'stop'); stop.setAttribute('offset', offset); gradient.append(stop); }
    defs.append(gradient); const path = document.createElementNS(ns, 'path'); path.setAttribute('fill', 'url(#' + gradient.id + ')');
    svg.append(defs, path); item.prepend(svg);
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; gaps.forEach((g, i) => Object.assign(g, { value: target(i), velocity: 0 })); paint(); } });
  paint();
  return dialogId => {
    selected = dialogId == null ? -1 : items.findIndex(item => item.querySelector('button').getAttribute('aria-controls') === dialogId);
    if (!frame) { stamp = 0; frame = requestAnimationFrame(tick); }
  };
}
