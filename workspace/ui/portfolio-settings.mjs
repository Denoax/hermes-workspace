import { predictSliderFlight, sliderFlightPoint, sliderValue } from './sliderFlight.mjs';
// Vanilla port of Mani's owned ThemeToggle / AngrySlider. Native button/range
// semantics remain authoritative; only their pointer-transparent vectors move.
export function installPortfolioSettings(audio, onAppearance) {
    const $ = id => document.getElementById(id), theme = $('theme'), motion = $('motion'), buddy = $('theme-buddy');
    const reduced = () => motion.value === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
    const apply = () => { buddy.setAttribute('aria-pressed', String(theme.value === 'dark')); buddy.setAttribute('aria-label', theme.value === 'dark' ? 'Light mode' : 'Dark mode'); $('less-motion').checked = motion.value === 'reduced'; };
    buddy.innerHTML = `<svg class="buddy-body theme-buddy" viewBox="0 0 64 64" aria-hidden="true"><defs><radialGradient id="buddy-material" cx="52%" cy="47%" r="61%"><stop offset=".48" stop-color="var(--buddy-body)"/><stop offset=".80" stop-color="var(--buddy-body)"/><stop offset="1" stop-color="var(--buddy-rim)"/></radialGradient><radialGradient id="buddy-light" cx="28%" cy="9%" r="76%"><stop stop-color="white" stop-opacity=".19"/><stop offset=".48" stop-color="white" stop-opacity="0"/></radialGradient></defs><path fill="url(#buddy-material)" d="M32 4C49 3 60 15 60 31C61 47 48 57 32 57C15 58 4 48 4 33C3 18 15 5 32 4Z"/><path fill="url(#buddy-light)" d="M32 4C49 3 60 15 60 31C61 47 48 57 32 57C15 58 4 48 4 33C3 18 15 5 32 4Z"/><g class="buddy-face" fill="var(--buddy-face)"><g class="buddy-awake"><circle cx="26" cy="25" r="3.6"/><circle cx="39" cy="25" r="3.6"/></g><g class="buddy-cross" fill="none" stroke="var(--buddy-face)" stroke-width="1.6" stroke-linecap="round"><path d="M23 23L29 29M29 23L23 29M36 23L42 29M42 23L36 29"/></g><g class="buddy-smile" fill="none" stroke="var(--buddy-face)" stroke-width="1.6" stroke-linecap="round"><path d="M22 26Q26 22 30 26M35 26Q39 22 43 26"/></g></g></svg>`;
    let raf = 0, last = 0, fx = 0, fy = 0, x = 0, y = 0, hover = false, down = false, reaction = 0;
    const draw = now => { raf = 0; if (!buddy.closest('dialog').open || document.hidden)
        return; const r = buddy.getBoundingClientRect(), dt = last ? Math.min(.05, (now - last) / 1000) : 1 / 60; last = now; const dx = x - r.left - r.width / 2, dy = y - r.top - r.height / 2, length = Math.max(160, Math.hypot(dx, dy)), tx = dx / length * 3.4, ty = dy / length * 3.4, k = 1 - Math.exp(-dt / .09); fx += (tx - fx) * k; fy += (ty - fy) * k; buddy.querySelector('.buddy-face').setAttribute('transform', `translate(${fx} ${fy})`); const react = Math.max(0, 1 - (now - reaction) / 480), happy = hover || react > 0; buddy.dataset.expression = down ? 'pressed' : happy ? 'smile' : 'awake'; buddy.querySelector('svg').style.transform = reduced() ? '' : `translateY(${-2 * Number(happy) + 1.5 * react}px) rotate(${fx * .8}deg) scale(${1 + .1 * Number(down) + .035 * react},${1 - .12 * Number(down) - .03 * react})`; if (!reduced() && (Math.abs(tx - fx) > .001 || Math.abs(ty - fy) > .001 || react > 0))
        raf = requestAnimationFrame(draw); };
    const wake = e => { if (e) {
        x = e.clientX;
        y = e.clientY;
    } if (!raf) {
        last = 0;
        raf = requestAnimationFrame(draw);
    } };
    buddy.addEventListener('pointermove', wake);
    buddy.addEventListener('pointerenter', e => { hover = true; wake(e); });
    buddy.addEventListener('pointerleave', e => { hover = false; down = false; wake(e); });
    buddy.addEventListener('pointerdown', e => { down = true; wake(e); });
    buddy.addEventListener('pointerup', e => { down = false; wake(e); });
    buddy.addEventListener('click', () => { theme.value = theme.value === 'dark' ? 'light' : 'dark'; reaction = performance.now(); apply(); onAppearance(); wake(); });
    $('less-motion').addEventListener('change', () => { motion.value = $('less-motion').checked ? 'reduced' : 'system'; onAppearance(); });
    const sliders = [];
    for (const [id, min, max, initial, update] of [['interface-volume', 0, 100, 12, n => audio.setVolume(n / 100)], ['interface-brightness', 80, 140, 100, n => document.getElementById('app').style.filter = n === 100 ? '' : `brightness(${n / 100})`]]) {
        const input = $(id), holder = input.closest('.owned-range'), svg = holder.querySelector('svg'), output = holder.querySelector('output');
        let value = initial, gesture = null, flightRaf = 0;
        try {
            const saved = Number(localStorage.getItem('hermes-ui:' + id));
            if (localStorage.getItem('hermes-ui:' + id) !== null && saved >= min && saved <= max)
                value = saved;
        }
        catch { }
        const normal = () => (value - min) / (max - min), length = () => Math.max(1, holder.getBoundingClientRect().width - 24);
        const drawPoint = (p, forecast = null) => { const width = holder.getBoundingClientRect().width, len = length(), cx = 12 + p.x * len, cy = 46 + p.y * len; svg.setAttribute('viewBox', `0 0 ${width} 94`); svg.querySelector('.slider-track').setAttribute('x2', String(width - 12)); const thumb = svg.querySelector('.slider-thumb'); thumb.setAttribute('cx', cx); thumb.setAttribute('cy', cy); svg.querySelector('.slider-fill').setAttribute('x2', 12 + normal() * len); svg.querySelector('.slider-tether').setAttribute('d', forecast ? `M${12 + gesture.anchor.x * len} 46Q${cx} 46 ${cx} ${cy}` : ''); let path = ''; if (forecast)
            for (let i = 0; i <= 20; i++) {
                const p = sliderFlightPoint(forecast, i / 20);
                path += (i ? 'L' : 'M') + (12 + p.x * len) + ' ' + (46 + p.y * len);
            } svg.querySelector('.slider-trajectory').setAttribute('d', path); };
        const commit = n => { value = Math.max(min, Math.min(max, Math.round(n))); input.value = value; output.value = value + '%'; update(value); try {
            localStorage.setItem('hermes-ui:' + id, String(value));
        }
        catch { } drawPoint({ x: normal(), y: 0 }); };
        const cancel = () => { gesture = null; cancelAnimationFrame(flightRaf); flightRaf = 0; holder.dataset.sliderPhase = 'idle'; drawPoint({ x: normal(), y: 0 }); };
        input.addEventListener('input', () => commit(Number(input.value)));
        holder.addEventListener('pointerdown', e => { if (e.button !== 0 || reduced())
            return; e.preventDefault(); input.focus({ preventScroll: true }); cancel(); holder.setPointerCapture(e.pointerId); const r = holder.getBoundingClientRect(), point = { x: (e.clientX - r.left - 12) / length(), y: (e.clientY - r.top - 46) / length() }; if (Math.abs(point.x - normal()) * length() > 16)
            commit(sliderValue(point.x, min, max)); gesture = { id: e.pointerId, anchor: { x: normal(), y: 0 }, raw: { x: normal(), y: 0 }, elastic: false }; holder.dataset.sliderPhase = 'drag'; });
        holder.addEventListener('pointermove', e => { if (!gesture || gesture.id !== e.pointerId)
            return; const r = holder.getBoundingClientRect(), p = { x: Math.max(-.6, Math.min(1.6, (e.clientX - r.left - 12) / length())), y: Math.max(-.6, Math.min(.6, (e.clientY - r.top - 46) / length())) }; gesture.raw = p; gesture.elastic ||= Math.abs(p.y) > .025 || p.x < -.015 || p.x > 1.015; if (gesture.elastic) {
            holder.dataset.sliderPhase = 'elastic';
            drawPoint(p, predictSliderFlight(gesture.anchor, p));
        }
        else {
            commit(sliderValue(p.x, min, max));
            gesture.anchor = { x: normal(), y: 0 };
        } });
        holder.addEventListener('pointerup', e => { if (!gesture || gesture.id !== e.pointerId)
            return; holder.releasePointerCapture(e.pointerId); if (!gesture.elastic) {
            cancel();
            return;
        } const flight = predictSliderFlight(gesture.anchor, gesture.raw), start = performance.now(); gesture = null; holder.dataset.sliderPhase = 'flight'; const animate = now => { const t = (now - start) / 1000 / flight.duration; drawPoint(sliderFlightPoint(flight, t)); if (t < 1 && !document.hidden && holder.closest('dialog').open)
            flightRaf = requestAnimationFrame(animate);
        else {
            commit(sliderValue(flight.target, min, max));
            cancel();
        } }; flightRaf = requestAnimationFrame(animate); });
        holder.addEventListener('pointercancel', cancel);
        holder.addEventListener('keydown', e => { if (e.key === 'Escape')
            cancel(); });
        window.addEventListener('blur', cancel);
        window.addEventListener('resize', cancel);
        holder.closest('dialog').addEventListener('close', cancel);
        document.addEventListener('visibilitychange', cancel);
        theme.addEventListener('change', cancel);
        motion.addEventListener('change', cancel);
        holder.closest('dialog').addEventListener('scroll', cancel, { passive: true });
        sliders.push({ reset: () => commit(initial), cancel, draw: () => drawPoint({ x: normal(), y: 0 }) });
        commit(value);
    }
    $('reset-settings').addEventListener('click', () => { sliders.forEach(s => s.reset()); audio.setEnabled(true); theme.value = 'dark'; motion.value = 'system'; apply(); onAppearance(); });
    $('appearance').addEventListener('close', () => { cancelAnimationFrame(raf); raf = 0; down = false; });
    document.addEventListener('visibilitychange', () => { if (document.hidden) {
        cancelAnimationFrame(raf);
        raf = 0;
    } });
    new ResizeObserver(() => sliders.forEach(s => s.draw())).observe($('appearance'));
    return { sync: () => { apply(); sliders.forEach(s => s.cancel()); } };
}
