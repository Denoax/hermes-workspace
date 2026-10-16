export type Rect = { left: number; top: number; right: number; bottom: number; width: number; height: number };
export type Viewport = { left: number; top: number; width: number; height: number };
export type Placement = "top-start" | "top-end" | "bottom-start" | "bottom-end";

/** Independent viewport placement for these bounded, non-nested app popovers.
 * Flip only when the requested side cannot fit and the other has more room;
 * preserve logical alignment, then constrain to the visual viewport. Not a
 * general Floating UI replacement for transformed/nested clipping contexts.
 */
export function placeOverlay(anchor: Rect, size: { width: number; height: number }, viewport: Viewport,
  preferred: Placement = "bottom-end", gap = 6, padding = 8) {
  const maxWidth = Math.max(0, viewport.width - padding * 2);
  const width = Math.min(size.width, maxWidth);
  const floor = viewport.top + viewport.height - padding;
  const ceiling = viewport.top + padding;
  const above = Math.max(0, anchor.top - gap - ceiling);
  const below = Math.max(0, floor - anchor.bottom - gap);
  const [wantedSide, align] = preferred.split("-");
  const side = wantedSide === "top"
    ? (size.height > above && below > above ? "bottom" : "top")
    : (size.height > below && above > below ? "top" : "bottom");
  const maxHeight = Math.min(viewport.height - padding * 2, side === "top" ? above : below);
  const height = Math.min(size.height, Math.max(0, maxHeight));
  const minimumX = viewport.left + padding;
  const maximumX = viewport.left + viewport.width - padding - width;
  const desiredX = align === "end" ? anchor.right - width : anchor.left;
  const left = Math.max(minimumX, Math.min(maximumX, desiredX));
  const desiredY = side === "top" ? anchor.top - gap - height : anchor.bottom + gap;
  const top = Math.max(ceiling, Math.min(floor - height, desiredY));
  const originX = Math.max(0, Math.min(width, anchor.left + anchor.width / 2 - left));
  return { left, top, maxWidth, maxHeight: Math.max(0, maxHeight),
    placement: `${side}-${align}` as Placement,
    transformOrigin: `${originX}px ${side === "top" ? height : 0}px` };
}

export function menuIndex(key: string, current: number, count: number) {
  if (!count) return -1;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (key === "ArrowDown") return current < 0 ? 0 : (current + 1) % count;
  if (key === "ArrowUp") return current < 0 ? count - 1 : (current - 1 + count) % count;
  return current;
}
