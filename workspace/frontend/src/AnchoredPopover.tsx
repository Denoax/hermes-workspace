import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { useReducedMotion } from "./lib/reduced-motion";
import { menuIndex, placeOverlay, type Placement } from "./lib/overlay-placement";

export function AnchoredPopover({ id, anchor, close, children, className, placement = "bottom-end", menu = false, label }:
  { id: string; anchor: HTMLElement; close: () => void; children: ReactNode; className: string;
    placement?: Placement; menu?: boolean; label: string }) {
  const surface = useRef<HTMLDivElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  const reduced = useReducedMotion();
  const focused = useRef(false);
  const typed = useRef({ value: "", at: 0 });
  const [position, setPosition] = useState<ReturnType<typeof placeOverlay> | null>(null);
  useLayoutEffect(() => {
    const node = surface.current!;
    let frame = 0;
    let live = true;
    const update = () => {
      if (!anchor.isConnected || !anchor.getClientRects().length) { closeRef.current(); return; }
      const viewport = window.visualViewport;
      setPosition(placeOverlay(anchor.getBoundingClientRect(),
        { width: node.offsetWidth, height: Math.max(node.offsetHeight, node.scrollHeight + 2) },
        { left: viewport?.offsetLeft ?? 0, top: viewport?.offsetTop ?? 0,
          width: viewport?.width ?? innerWidth, height: viewport?.height ?? innerHeight }, placement));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; if (live) update(); });
    };
    const outside = (event: PointerEvent) => {
      const path = event.composedPath();
      if (!path.includes(node) && !path.includes(anchor)) closeRef.current();
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      closeRef.current();
      if (anchor.isConnected) anchor.focus({ preventScroll: true });
    };
    update();
    const resize = new ResizeObserver(schedule);
    resize.observe(node);
    resize.observe(anchor);
    addEventListener("resize", schedule);
    addEventListener("scroll", schedule, true);
    addEventListener("pointerdown", outside, true);
    addEventListener("keydown", keydown, true);
    window.visualViewport?.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("scroll", schedule);
    return () => {
      live = false;
      if (frame) cancelAnimationFrame(frame);
      resize.disconnect();
      removeEventListener("resize", schedule);
      removeEventListener("scroll", schedule, true);
      removeEventListener("pointerdown", outside, true);
      removeEventListener("keydown", keydown, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      // Preserve focus in a newly opened dialog or where an outside click moved it.
      if (node.contains(document.activeElement) && anchor.isConnected && !document.querySelector('dialog[open]'))
        anchor.focus({ preventScroll: true });
    };
  }, [anchor, placement, menu]);
  useLayoutEffect(() => {
    if (!position || focused.current) return;
    const node = surface.current!;
      const target = menu ? node.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled):not([aria-disabled="true"])')
      : node.querySelector<HTMLElement>('input:not(:disabled),button:not(:disabled),select:not(:disabled)');
    if (menu) node.querySelectorAll<HTMLElement>('[role="menuitem"]').forEach(item => { item.tabIndex = item === target ? 0 : -1; });
    target?.focus({ preventScroll: true });
    focused.current = true;
  }, [position, menu]);
  return createPortal(<motion.div ref={surface} id={id} role={menu ? "menu" : "dialog"}
    aria-label={label} className={className + " anchored-popover"}
    data-placement={position?.placement}
    initial={{ opacity: 0, scale: reduced ? 1 : 0.98 }}
    animate={{ opacity: position ? 1 : 0, scale: 1 }}
    transition={{ duration: reduced ? 0 : 0.14, ease: [0.16, 1, 0.3, 1] }}
    style={{ position: "fixed", left: position?.left ?? 0, top: position?.top ?? 0,
      visibility: position ? "visible" : "hidden", maxWidth: position?.maxWidth,
      maxHeight: position?.maxHeight, transformOrigin: position?.transformOrigin }}
    onBlur={(event) => {
      const next = event.relatedTarget as Node | null;
      if (next && !event.currentTarget.contains(next) && next !== anchor) closeRef.current();
    }}
    onKeyDown={(event) => {
      if (!menu) return;
      const items = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled):not([aria-disabled="true"])')];
      const current = items.indexOf(document.activeElement as HTMLElement);
      const focus = (target: HTMLElement) => { items.forEach(item => { item.tabIndex = item === target ? 0 : -1; }); target.focus(); };
      if (event.key === "Tab") {
        const targets = [...document.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')]
          .filter(item => item.tabIndex >= 0 && !event.currentTarget.contains(item) && item.getClientRects().length && !item.closest('[inert]'));
        const next = targets[targets.indexOf(anchor) + (event.shiftKey ? -1 : 1)];
        event.preventDefault();
        closeRef.current();
        (next ?? anchor).focus({ preventScroll: true });
        return;
      }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        const index = menuIndex(event.key, current, items.length);
        if (index >= 0) { event.preventDefault(); focus(items[index]); }
      } else if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey && event.key !== " ") {
        const now = performance.now();
        typed.current.value = (now - typed.current.at < 600 ? typed.current.value : "") + event.key.toLocaleLowerCase();
        typed.current.at = now;
        const ordered = [...items.slice(current + 1), ...items.slice(0, current + 1)];
        const target = ordered.find(item => item.textContent?.trim().toLocaleLowerCase().startsWith(typed.current.value));
        if (target) focus(target);
      }
    }}>{children}</motion.div>, document.body);
}
