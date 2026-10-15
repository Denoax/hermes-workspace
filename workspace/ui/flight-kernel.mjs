// One sampled pose owns both GL instance paint and native arrival eligibility.
// v25 timing/4px aperture cohorts ported from Mani's owned emission recipe.
export const OPEN_SECONDS = .82, CLOSE_SECONDS = .44, TILE_BUDGET = 32768;
const clamp = n => Math.max(0, Math.min(1, n));
export function seed(index) { let n = Math.imul(index + 1, 1597334677); n ^= n >>> 16; return (n >>> 0) / 4294967295; }
export function bezier(start, c1, c2, end, t, duration) {
    const u = 1 - t;
    return { value: u * u * u * start + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t * t * t * end,
        velocity: (3 * u * u * (c1 - start) + 6 * u * t * (c2 - c1) + 3 * t * t * (end - c2)) / duration };
}
export function openingCell(index, x, y, width, height, source, target) {
    const random = seed(index), birth = .18 * (.6 * random + .4 * y / target.height);
    const tx = target.left + x, ty = target.top + y;
    const sx = source.left + source.width * (.14 + .72 * random), sy = source.bottom;
    const duration = .50 + .10 * y / target.height + .04 * seed(index + 99);
    return { x, y, width, height, birth, duration, start: birth, end: birth + duration,
        from: { x: sx, y: sy, a: 0 }, c1: { x: sx, y: sy + 24 },
        c2: { x: tx + (random - .5) * Math.min(64, target.width * .14), y: ty - 32 }, to: { x: tx, y: ty, a: 1 }, born: false };
}
export function sampleCell(cell, time) {
    const t = clamp((time - cell.start) / cell.duration), born = time >= cell.start && (cell.born || cell.to.a > 0);
    const x = bezier(cell.from.x, cell.c1.x, cell.c2.x, cell.to.x, t, cell.duration);
    const y = bezier(cell.from.y, cell.c1.y, cell.c2.y, cell.to.y, t, cell.duration);
    const fade = cell.to.a > 0 ? clamp((time - cell.start) / .06) : 1 - Math.pow(t, 3);
    const a = cell.to.a > 0 ? cell.from.a + (cell.to.a - cell.from.a) * fade : cell.from.a * fade;
    return { x: x.value, y: y.value, vx: t >= 1 ? 0 : x.velocity, vy: t >= 1 ? 0 : y.velocity, a: born ? a : 0, born, arrived: time >= cell.end && cell.to.a === 1 };
}
export function retargetCell(cell, pose, time, destination, opening) {
    // A never-born cell cannot appear during close. Velocity is continuous at reversal.
    const duration = opening ? .44 : CLOSE_SECONDS;
    const start = opening && !pose.born ? time + cell.birth : time;
    return { ...cell, start, end: start + duration, duration, born: pose.born,
        from: { x: pose.x, y: pose.y, a: pose.a }, c1: { x: pose.x + pose.vx * duration / 3, y: pose.y + pose.vy * duration / 3 },
        c2: { x: destination.x, y: destination.y + (opening ? -24 : 24) }, to: { ...destination, a: opening ? 1 : 0 } };
}
export function arrivedFront(cells, poses, height) {
    let front = 0;
    for (let i = 0; i < cells.length;) {
        const row = cells[i].y;
        let ready = true, bottom = row;
        while (i < cells.length && cells[i].y === row) {
            ready &&= poses[i].arrived;
            bottom = Math.max(bottom, row + cells[i].height);
            i++;
        }
        if (!ready)
            break;
        front = bottom;
    }
    return Math.min(front, height);
}
