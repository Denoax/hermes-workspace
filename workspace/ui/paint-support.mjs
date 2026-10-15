// Source-derived runtime paint adaptations for the assistant's native values
// and owned SVG gradients. These pixels are transient, never saved as assets.
export function svgFill(element, svg, ctx, fill) {
    const id = fill.match(/#([^\s"')]+)/)?.[1], gradient = id && svg.querySelector('#' + CSS.escape(id));
    if (!gradient?.matches('radialGradient,linearGradient'))
        return fill;
    const box = element.getBBox(), fraction = (name, fallback) => { const raw = gradient.getAttribute(name); return raw?.endsWith('%') ? parseFloat(raw) / 100 : Number(raw ?? fallback); };
    ctx.save();
    ctx.translate(box.x, box.y);
    ctx.scale(box.width || 1, box.height || 1);
    const stops = [...gradient.querySelectorAll('stop')];
    ctx.restore();
    if (stops.length) {
        ctx.save();
        ctx.translate(box.x, box.y);
        ctx.scale(box.width || 1, box.height || 1);
        const result = gradient.matches('radialGradient') ? ctx.createRadialGradient(fraction('cx', .5), fraction('cy', .5), 0, fraction('cx', .5), fraction('cy', .5), fraction('r', .5)) : ctx.createLinearGradient(fraction('x1', 0), fraction('y1', 0), fraction('x2', 1), fraction('y2', 0));
        for (const stop of stops) {
            const s = getComputedStyle(stop), raw = stop.getAttribute('offset') || '0', offset = raw.endsWith('%') ? parseFloat(raw) / 100 : Number(raw), parts = s.stopColor.match(/[\d.]+/g);
            result.addColorStop(Math.max(0, Math.min(1, offset)), parts ? `rgba(${parts.slice(0, 3).join(',')},${s.stopOpacity})` : s.stopColor);
        }
        ctx.restore();
        return result;
    }
    return fill;
}
export function paintValues(node, ctx, origin, visible) {
    for (const element of node.querySelectorAll('textarea,input:not([type=range]):not([type=checkbox]),select')) {
        if (!visible(element))
            continue;
        const rect = element.getBoundingClientRect(), style = getComputedStyle(element), x = rect.left - origin.left, y = rect.top - origin.top;
        const text = element instanceof HTMLSelectElement ? element.selectedOptions[0]?.textContent : element.value || element.placeholder;
        if (!text)
            continue;
        ctx.save();
        ctx.beginPath();
        ctx.rect(x, y, rect.width, rect.height);
        ctx.clip();
        ctx.fillStyle = style.color;
        ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        ctx.textBaseline = 'top';
        const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.6, padX = parseFloat(style.paddingLeft), padY = parseFloat(style.paddingTop);
        const lines = text.split('\n'), first = Math.max(0, Math.floor(element.scrollTop / lineHeight));
        for (let i = first; i < Math.min(lines.length, first + Math.ceil(rect.height / lineHeight) + 1); i++)
            ctx.fillText(lines[i], x + padX - element.scrollLeft, y + padY + i * lineHeight - element.scrollTop);
        ctx.restore();
    }
}
