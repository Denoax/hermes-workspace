import { paintPane } from './paintPane.mjs';
import { glassOptics } from './glassOptics.mjs';
import { openingCell, sampleCell, retargetCell, arrivedFront, TILE_BUDGET } from './flight-kernel.mjs';
export function placePane(trigger, pane, viewport) {
    const pad = 12, gap = 10, width = Math.min(pane.width, Math.max(0, viewport.width - 24)), height = Math.min(pane.height, Math.max(0, viewport.height - 24));
    const left = Math.max(pad, Math.min(trigger.right - width, viewport.width - width - pad)), below = trigger.bottom + gap;
    return { left, top: below + height <= viewport.height - pad ? below : Math.max(pad, Math.min(trigger.top - height - gap, viewport.height - height - pad)), width, height };
}
export function positionPane(pane, trigger) {
    if (pane.id === 'files-panel') {
        pane.style.setProperty('--files-top', Math.ceil(document.querySelector('.toolbar').getBoundingClientRect().bottom + 12) + 'px');
        return;
    }
    if (!trigger?.getBoundingClientRect || innerWidth < 820) {
        pane.removeAttribute('data-anchored');
        pane.style.removeProperty('left');
        pane.style.removeProperty('top');
        return;
    }
    const p = placePane(trigger.getBoundingClientRect(), pane.getBoundingClientRect(), { width: innerWidth, height: innerHeight });
    pane.dataset.anchored = 'true';
    pane.style.left = Math.round(p.left * devicePixelRatio) / devicePixelRatio + 'px';
    pane.style.top = Math.round(p.top * devicePixelRatio) / devicePixelRatio + 'px';
}
const fields = new Map(), paintCache = new WeakMap();
let backdropRevision = 0, backdropFrame = 0;
function invalidateBackdrop() {
    backdropRevision++;
    if (document.hidden || backdropFrame || ![...fields.values()].some(f => f.pane.open)) return;
    backdropFrame = requestAnimationFrame(() => {
        backdropFrame = 0;
        for (const field of fields.values()) {
            if (!field.pane.open) continue;
            try { field.atlas = atlas(field.pane, field.rect); }
            catch (error) { metrics.fallbacks.push(error.message); cancelPaneMotion(field.pane); field.pane.dataset.glassMode = 'static'; }
        }
        // Atlas paint borrows the shared GL canvas. Restore all active flight
        // paint in the same frame, so scratch lens pixels never reach the screen.
        if ([...fields.values()].some(f => f.moving)) {
            cancelAnimationFrame(frame); frame = 0; render(performance.now());
        }
    });
}
new MutationObserver(invalidateBackdrop).observe(document.getElementById('messages'), { childList: true, subtree: true, characterData: true });
document.getElementById('messages').addEventListener('scroll', invalidateBackdrop, { passive: true });
let layer, canvas, gl, program, buffer, texture, frame = 0, lastFrame = 0;
const metrics = { frames: 0, paintMs: [], frameIntervals: [], fallbacks: [], renders: 0, active: 0, cacheHits: 0, tilePeak: 0, tileSteps: [], submitMs: [], contextLosses: 0 };
// Counts only CPU submission/paint and RAF intervals; never reported as GPU timings.
Object.defineProperty(globalThis, 'hermesPaneMetrics', { get: () => ({ ...metrics, active: [...fields.values()].filter(f => f.moving).length, rafPending: !!frame || !!backdropFrame }) });
const vertex = `#version 300 es
precision highp float;in vec4 aRect;in vec4 aUV;in float aAlpha;uniform vec2 uSize;out vec2 vUV;out float vAlpha;
void main(){vec2 q=vec2(float(gl_VertexID==1||gl_VertexID==3),float(gl_VertexID>=2));vec2 p=aRect.xy+q*aRect.zw;gl_Position=vec4(p/uSize*vec2(2.,-2.)+vec2(-1.,1.),0.,1.);vUV=aUV.xy+q*aUV.zw;vAlpha=aAlpha;}`;
const fragment = `#version 300 es
precision highp float;uniform sampler2D uPaint;in vec2 vUV;in float vAlpha;out vec4 color;void main(){color=texture(uPaint,vUV);color.a*=vAlpha;}`;
// Direct vanilla GLSL port of owned GlassLayer.tsx: rounded SDF, magnification,
// bounded rim displacement, chromatic fringe, four-tap roughness and edge light.
const glassFragment = `#version 300 es
precision highp float;uniform sampler2D uPaint;uniform vec2 uSize,uOrigin,uPane;uniform vec4 uOptics,uFilm;uniform float uDpr,uRadius;out vec4 color;
void main(){vec2 p=vec2(gl_FragCoord.x/uDpr,uPane.y-gl_FragCoord.y/uDpr);vec2 local=p-uPane*.5;vec2 q=abs(local)-uPane*.5+uRadius;float distance=length(max(q,0.))+min(max(q.x,q.y),0.)-uRadius;float aa=1./uDpr;if(distance>aa)discard;vec2 normal=q.x>0.&&q.y>0.?normalize(max(q,0.))*sign(local):(q.x>q.y?vec2(sign(local.x),0.):vec2(0.,sign(local.y)));float bevel=uOptics.x;float rim=clamp(1.+distance/bevel,0.,1.);float shift=bevel*.19*rim*rim*(3.-2.*rim);vec2 uv=(uOrigin+uPane*.5+local/uOptics.y)/uSize;vec2 bend=normal*shift/uSize;vec2 rgb=normal*uOptics.z*rim*rim/uSize;vec3 c=vec3(texture(uPaint,clamp(uv-bend-rgb,0.,1.)).r,texture(uPaint,clamp(uv-bend,0.,1.)).g,texture(uPaint,clamp(uv-bend+rgb,0.,1.)).b);vec2 rough=vec2(uOptics.w)/uSize;vec3 soft=(texture(uPaint,uv-bend+vec2(rough.x,0.)).rgb+texture(uPaint,uv-bend-vec2(rough.x,0.)).rgb+texture(uPaint,uv-bend+vec2(0.,rough.y)).rgb+texture(uPaint,uv-bend-vec2(0.,rough.y)).rgb)*.25;c=mix(c,soft,.24);c+=vec3(pow(rim,3.)*(.012+.07*max(0.,dot(normal,normalize(vec2(-.5,-1.))))))+pow(rim,2.)*.005;/* source DOM film applied once */c=mix(c,uFilm.rgb,uFilm.a);color=vec4(c,1.-smoothstep(-aa,aa,distance));}`;
function compile(type, source) { const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw Error('pane_shader_compile'); return s; }
function link(v, f) { const p = gl.createProgram(); gl.attachShader(p, compile(gl.VERTEX_SHADER, v)); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, f)); gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS))
    throw Error('pane_shader_link'); return p; }
function init() {
    if (gl)
        return;
    layer?.remove();
    layer = document.createElement('div');
    layer.className = 'pane-flight-layer';
    layer.setAttribute('popover', 'manual');
    layer.setAttribute('aria-hidden', 'true');
    layer.inert = true;
    canvas = document.createElement('canvas');
    layer.append(canvas);
    document.body.append(layer);
    gl = canvas.getContext('webgl2', { alpha: true, premultipliedAlpha: true, antialias: false, preserveDrawingBuffer: true });
    if (!gl)
        throw Error('WebGL2_unavailable');
    program = link(vertex, fragment);
    buffer = gl.createBuffer();
    texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); metrics.contextLosses++; for (const f of fields.values())
        finish(f); stop(); metrics.fallbacks.push('context_lost_owned_static'); gl = null; });
}
function upload(image) { gl.bindTexture(gl.TEXTURE_2D, texture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image); }
function backdrop() {
    // Capture this application's real DOM substrate; no invented portfolio scene.
    const base = paintPane(document.getElementById('app'), innerWidth, innerHeight), ctx = base.getContext('2d');
    ctx.save();
    ctx.globalCompositeOperation = 'destination-over';
    ctx.fillStyle = getComputedStyle(document.body).backgroundColor;
    ctx.fillRect(0, 0, base.width, base.height);
    ctx.restore();
    return base;
}
function atlas(pane, rect) {
    const key = [rect.x, rect.y, rect.width, rect.height, devicePixelRatio, document.documentElement.dataset.theme, backdropRevision, pane.innerText, ...[...pane.querySelectorAll('input,textarea,select')].map(e => e.value + e.checked)].join('|');
    const cached = paintCache.get(pane);
    if (cached?.key === key) {
        pane.querySelector('.pane-glass')?.remove();
        pane.prepend(cached.lens);
        pane.dataset.glassMode = 'gpu';
        metrics.cacheHits++;
        return cached.image;
    }
    const started = performance.now(), dpr = Math.min(devicePixelRatio, 2048 / Math.max(rect.width, rect.height));
    const paint = paintPane(pane, rect.width, rect.height), back = backdrop();
    const radius = parseFloat(getComputedStyle(pane).borderRadius) || 30, film = (getComputedStyle(pane).getPropertyValue('--glass-film') || 'rgba(16,19,24,.64)').match(/[\d.]+/g).map(Number);
    const optical = glassOptics(rect.width, rect.height, radius, true), glassProgram = link(`#version 300 es\nvoid main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));gl_Position=vec4(p*2.-1.,0.,1.);}`, glassFragment);
    canvas.width = Math.ceil(rect.width * dpr);
    canvas.height = Math.ceil(rect.height * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA,gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(glassProgram);
    upload(back);
    const uniform = (name, ...value) => gl['uniform' + value.length + 'f'](gl.getUniformLocation(glassProgram, name), ...value);
    uniform('uSize', innerWidth, innerHeight);
    uniform('uOrigin', rect.left, rect.top);
    uniform('uPane', rect.width, rect.height);
    uniform('uOptics', optical.bevel, optical.magnification, optical.fringe, optical.roughness);
    uniform('uDpr', dpr);
    uniform('uRadius', radius);
    uniform('uFilm', film[0] / 255, film[1] / 255, film[2] / 255, film[3]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    const lens = document.createElement('canvas');
    lens.className = 'pane-glass';
    lens.setAttribute('aria-hidden', 'true');
    lens.width = canvas.width;
    lens.height = canvas.height;
    lens.getContext('2d').drawImage(canvas, 0, 0);
    pane.querySelector('.pane-glass')?.remove();
    pane.prepend(lens);
    pane.dataset.glassMode = 'gpu';
    const result = document.createElement('canvas');
    result.width = canvas.width;
    result.height = canvas.height;
    const ctx = result.getContext('2d');
    ctx.drawImage(lens, 0, 0);
    ctx.drawImage(paint, 0, 0, paint.width, paint.height, 0, 0, result.width, result.height);
    paintCache.set(pane, { key, lens, image: result });
    gl.deleteProgram(glassProgram);
    metrics.paintMs.push(performance.now() - started);
    if (metrics.paintMs.length > 100)
        metrics.paintMs.shift();
    return result;
}
function resizeCanvas() {
    const width = Math.ceil(innerWidth * devicePixelRatio), height = Math.ceil(innerHeight * devicePixelRatio);
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    canvas.style.width = innerWidth + 'px'; canvas.style.height = innerHeight + 'px';
    gl.viewport(0, 0, canvas.width, canvas.height);
}
function setFront(f, front) {
    f.front = front;
    if (!f.pane.open)
        return;
    f.pane.style.maskImage = front<f.rect.height ? `linear-gradient(to bottom,#000 ${Math.max(0,front-8)}px,transparent ${front}px)` : '';
    f.pane.style.clipPath = `inset(0 0 ${Math.max(0, f.rect.height - front)}px 0 round ${f.radius}px)`;
    for (const control of f.pane.querySelectorAll('button,input,select,textarea,a')) {
        const bottom = control.getBoundingClientRect().bottom - f.rect.top;
        control.inert = bottom > (front===f.rect.height?front:Math.max(0,front-8));
    }
}
function restore(pane) { pane.style.removeProperty('clip-path');
    pane.style.removeProperty('mask-image'); pane.querySelectorAll('[inert]').forEach(e => e.inert = false); pane.dataset.flight = 'settled'; }
function finish(f) { f.moving = false; if (f.pane.open) {
    restore(f.pane);
    if (f.pane.id === 'input-dialog')
        document.getElementById('input-value').focus({ preventScroll: true });
    if (f.pane.id === 'project-dialog')
        document.getElementById('project-search').focus({ preventScroll: true });
}
else {
    f.pane.querySelector('.pane-glass')?.remove();
    fields.delete(f.pane);
} }
function stop() { cancelAnimationFrame(frame); frame = 0; lastFrame = 0; layer?.hidePopover(); }
function schedule() { if (!document.hidden && !frame) {
    layer.showPopover();
    frame = requestAnimationFrame(render);
} }
function render(now) {
    const submitted = performance.now();
    frame = 0;
    metrics.frames++;
    if (lastFrame) {
        metrics.frameIntervals.push(now - lastFrame);
        if (metrics.frameIntervals.length > 1800)
            metrics.frameIntervals.shift();
    }
    lastFrame = now;
    resizeCanvas();
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(program);
    gl.uniform2f(gl.getUniformLocation(program, 'uSize'), innerWidth, innerHeight);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    for (const f of fields.values()) {
        if (!f.moving)
            continue;
        const time = (now - f.started) / 1000, poses = f.cells.map(c => sampleCell(c, time));
        if (f.opening)
            setFront(f, Math.max(f.front, arrivedFront(f.cells, poses, f.rect.height)));
        const vertices = [];
        for (let i = 0; i < f.cells.length; i++) {
            const c = f.cells[i], p = poses[i];
            if (!p.born || p.a <= 0 || f.opening && c.y + c.height <= Math.max(0,f.front-8))
                continue;
            vertices.push(p.x, p.y, c.width, c.height, c.x / f.rect.width, c.y / f.rect.height, c.width / f.rect.width, c.height / f.rect.height, p.a);
        }
        metrics.tilePeak = Math.max(metrics.tilePeak, vertices.length / 9);
        upload(f.atlas);
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.DYNAMIC_DRAW);
        for (const [name, size, offset] of [['aRect', 4, 0], ['aUV', 4, 16], ['aAlpha', 1, 32]]) {
            const loc = gl.getAttribLocation(program, name);
            gl.enableVertexAttribArray(loc);
            gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 36, offset);
            gl.vertexAttribDivisor(loc, 1);
        }
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, vertices.length / 9);
        metrics.renders++;
        if (time >= Math.max(...f.cells.map(c => c.end)))
            finish(f);
    }
    metrics.submitMs.push(performance.now() - submitted);
    if (metrics.submitMs.length > 1800)
        metrics.submitMs.shift();
    if ([...fields.values()].some(f => f.moving))
        schedule();
    else
        stop();
}
function retarget(f, opening) {
    const time = (performance.now() - f.started) / 1000;
    f.cells = f.cells.map(c => { const p = sampleCell(c, time); const destination = opening ? { x: f.rect.left + c.x, y: f.rect.top + c.y } : { x: f.source.left + f.source.width * .5, y: f.source.bottom }; return retargetCell(c, p, time, destination, opening); });
    f.opening = opening;
    f.moving = true;
    f.pane.dataset.flight = opening ? 'opening' : 'closing';
    schedule();
}
export function cancelPaneMotion(pane) { const f = fields.get(pane); if (f)
    finish(f); restore(pane); if (![...fields.values()].some(x => x.moving))
    stop(); }
export function dismissPane(pane) { const f = fields.get(pane); if (!f || document.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.motion === 'reduced') {
    cancelPaneMotion(pane);
    fields.delete(pane);
    return;
} retarget(f, false); restore(pane); }
export function revealPane(pane, trigger, reduced) {
    positionPane(pane, trigger);
    if (reduced || document.hidden || !trigger?.getBoundingClientRect) {
        cancelPaneMotion(pane);
        return;
    }
    try {
        init();
    // Reinsert paint above a newly opened modal without acquiring input.
    layer.hidePopover();layer.showPopover();
        const old = fields.get(pane), rect = pane.getBoundingClientRect();
        if (old && old.moving) {
            if (!old.opening)
                old.front = 0;
            old.rect = rect;
            old.source = trigger.getBoundingClientRect();
            setFront(old, old.front);
            retarget(old, true);
            return;
        }
        const source = trigger.getBoundingClientRect(), available = TILE_BUDGET - [...fields.values()].filter(f => f.moving && f.pane !== pane).reduce((n, f) => n + f.cells.length, 0);
        if (available < 256 || [...fields.values()].filter(f => f.moving).length >= 4)
            throw Error('tile_budget_owned_static');
        let step = 4;
        while (Math.ceil(rect.width / step) * Math.ceil(rect.height / step) > available)
            step++;
        metrics.tileSteps.push({ pane: pane.id, step, width: rect.width, height: rect.height });
        restore(pane);
        const image = atlas(pane, rect), cells = [];
        for (let y = 0; y < rect.height; y += step)
            for (let x = 0; x < rect.width; x += step)
                cells.push(openingCell(cells.length, x, y, Math.min(step, rect.width - x), Math.min(step, rect.height - y), source, rect));
        const f = { pane, rect, source, radius: parseFloat(getComputedStyle(pane).borderRadius) || 30, atlas: image, cells, front: 0, started: performance.now(), opening: true, moving: true };
        fields.set(pane, f);
        pane.dataset.flight = 'opening';
        setFront(f, 0);
        schedule();
    }
    catch (error) {
        metrics.fallbacks.push(error.message);
        pane.dataset.glassMode = 'static';
        cancelPaneMotion(pane);
    }
}
export function refreshPane(pane, trigger) {
    const f = fields.get(pane);
    positionPane(pane, trigger);
    if (!f || !gl)
        return;
    const rect = pane.getBoundingClientRect();
    try {
        f.atlas = atlas(pane, rect);
        const sx = rect.width / f.rect.width, sy = rect.height / f.rect.height;
        for (const c of f.cells) {
            c.x *= sx;
            c.y *= sy;
            c.width *= sx;
            c.height *= sy;
        }
        f.rect = rect;
        if (f.moving) {
            f.front = 0;
            retarget(f, true);
        }
    }
    catch (error) {
        metrics.fallbacks.push(error.message);
        cancelPaneMotion(pane);
        pane.dataset.glassMode = 'static';
    }
}
document.addEventListener('visibilitychange', () => { if (document.hidden) {
    cancelAnimationFrame(backdropFrame);backdropFrame=0;
    for (const f of fields.values())
        finish(f);
    stop();
} });
