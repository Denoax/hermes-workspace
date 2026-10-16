import { useLayoutEffect, useRef, useState, type ReactNode, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { motion, useIsPresent } from "motion/react";
import { useReducedMotion } from "./lib/reduced-motion";
import { containModalTab, releaseSurface, workspaceSurface } from "./lib/workspace-surface";
export function Panel({ title, close, children, returnFocusTo }: {
  title: string; close: () => void; children: ReactNode; returnFocusTo?: HTMLElement | null;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const present = useIsPresent();
  const presentRef = useRef(present);
  presentRef.current = present;
  const closeRef = useRef(close);
  closeRef.current = close;
  const reduced = useReducedMotion();
  const requestedSheet = title === "Files" || title === "Details";
  const [surface, setSurface] = useState<"sheet" | "modal">(requestedSheet ? "sheet" : "modal");
  const release = useRef<(restore: boolean) => void>(() => {});
  const dismiss = (restore = true) => {
    release.current(restore);
    closeRef.current();
  };
  useLayoutEffect(() => {
    if (!present) return;
    const before = document.activeElement as HTMLElement | null;
    const triggerId = ({ Files: "files-toggle", Details: "diagnostics", Settings: "settings-toggle" } as Record<string, string>)[title];
    const trigger = returnFocusTo ?? (triggerId ? document.getElementById(triggerId) : null) ?? before;
    const dialog = ref.current!;
    let mode: "sheet" | "modal" | null = null;
    let released = false;
    const focusContent = () => {
      const target = dialog.querySelector<HTMLElement>(
        '[autofocus],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),button:not(:disabled):not([data-action="close-dialog"])',
      ) ?? dialog.querySelector<HTMLElement>('[data-action="close-dialog"]');
      target?.focus({ preventScroll: true });
    };
    release.current = restore => {
      if (released) return;
      released = true;
      releaseSurface(dialog, trigger, restore);
    };
    const composer = document.querySelector<HTMLElement>(".composer-area");
    const toolbar = document.querySelector<HTMLElement>(".toolbar");
    const layout = () => {
      if (released || !presentRef.current) return;
      const viewport = window.visualViewport;
      const area = { left: viewport?.offsetLeft ?? 0, top: viewport?.offsetTop ?? 0,
        width: viewport?.width ?? innerWidth, height: viewport?.height ?? innerHeight };
      const bounds = requestedSheet ? workspaceSurface(area,
        toolbar?.getBoundingClientRect().bottom ?? area.top,
        composer?.getBoundingClientRect().top ?? area.top + area.height) : null;
      const nextMode = bounds?.mode ?? "modal";
      const focused = dialog.contains(document.activeElement) ? document.activeElement as HTMLElement : null;
      if (nextMode !== mode) {
        if (dialog.open) dialog.close();
        mode = nextMode;
        dialog.dataset.surface = mode;
        setSurface(mode);
        if (mode === "sheet") dialog.show(); else dialog.showModal();
        dialog.inert = false;
        if (focused?.isConnected) focused.focus({ preventScroll: true }); else focusContent();
      }
      if (bounds) {
        dialog.dataset.sheetFallback = bounds.mode === "modal" ? "true" : "false";
        Object.assign(dialog.style, { inset: `${bounds.top}px auto auto ${bounds.left}px`,
          width: `${bounds.width}px`, maxWidth: `${bounds.width}px`,
          height: `${bounds.height}px`, maxHeight: `${bounds.height}px`, margin: "0" });
      }
    };
    const resize = new ResizeObserver(layout);
    if (requestedSheet && composer) resize.observe(composer);
    if (requestedSheet && toolbar) resize.observe(toolbar);
    layout();
    if (requestedSheet) {
      addEventListener("resize", layout);
      window.visualViewport?.addEventListener("resize", layout);
      window.visualViewport?.addEventListener("scroll", layout);
    }
    const outside = (event: PointerEvent) => {
      if (!presentRef.current || mode !== "sheet") return;
      const target = event.target as HTMLElement;
      if (!dialog.contains(target) && !target.closest(".toolbar-actions")) dismiss(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (presentRef.current && mode === "sheet" && event.key === "Escape") {
        event.preventDefault(); dismiss();
      }
    };
    addEventListener("pointerdown", outside);
    // Native modal Escape is owned by onCancel; sheets need the non-modal route.
    if (requestedSheet) addEventListener("keydown", escape);
    return () => {
      release.current(true);
      resize.disconnect();
      if (requestedSheet) {
        removeEventListener("resize", layout);
        window.visualViewport?.removeEventListener("resize", layout);
        window.visualViewport?.removeEventListener("scroll", layout);
      }
      removeEventListener("pointerdown", outside);
      if (requestedSheet) removeEventListener("keydown", escape);
    };
    // AnimatePresence may reuse this node when an exit is interrupted. Re-enter
    // its native top layer as well as its animation on each present transition.
  }, [present, title, requestedSheet, returnFocusTo]);
  const sheet = surface === "sheet";
  return createPortal(
    <motion.dialog ref={ref} className="panel" data-surface={sheet ? "sheet" : "modal"}
      data-settings={title === "Settings" || undefined}
      initial={{ opacity: sheet ? 1 : 0, x: reduced || !sheet ? 0 : 12, y: reduced || sheet ? 0 : 6, scale: reduced || sheet ? 1 : 0.99 }}
      animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
      exit={{ opacity: sheet ? 1 : 0, x: reduced || !sheet ? 0 : 8, y: reduced || sheet ? 0 : 4, scale: 1 }}
      transition={{ duration: reduced ? 0 : 0.16, ease: [0.16, 1, 0.3, 1] }}
      style={{ pointerEvents: present ? "auto" : "none", transformOrigin: sheet ? "right center" : "center" }}
      aria-label={title}
      onKeyDown={event => containModalTab(event.currentTarget, event)}
      onCancel={event => { event.preventDefault(); dismiss(); }}
      onClick={event => {
        if (sheet || event.target !== event.currentTarget) return;
        const r = event.currentTarget.getBoundingClientRect();
        if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dismiss();
      }}>
      <header><h2>{title}</h2><button className="icon-button" data-action="close-dialog" aria-label={"Close " + title} onClick={() => dismiss()}>×</button></header>
      {children}
    </motion.dialog>, document.body);
}
export function Brain({ on }: { on: boolean }) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className={on ? "brain-icon brain-on" : "brain-icon"}
    >
      <defs>
        <linearGradient
          id="brain-surface"
          x1="8"
          y1="4"
          x2="32"
          y2="36"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor={on ? "#e5b7ff" : "#ffc8df"} />
          <stop offset=".52" stopColor={on ? "#bd7ae7" : "#f398c7"} />
          <stop offset="1" stopColor={on ? "#8a51b8" : "#d96ca8"} />
        </linearGradient>
      </defs>
      <g
        className="brain-lobes"
        fill="url(#brain-surface)"
        stroke="#963962"
        strokeWidth="1.1"
        strokeLinejoin="round"
      >
        <path d="M18.8 8.7C17.8 4 11.4 4.6 10.6 8.8C6 8.1 3.5 12.7 5.7 16.3C1.6 19.2 3.6 25.4 7.5 26.1C6.9 31 11.8 34 15.4 31.9C17.2 35.1 20 32.6 19.2 29.8Z" />
        <path d="M21.2 8.7C22.2 4 28.6 4.6 29.4 8.8C34 8.1 36.5 12.7 34.3 16.3C38.4 19.2 36.4 25.4 32.5 26.1C33.1 31 28.2 34 24.6 31.9C22.8 35.1 20 32.6 20.8 29.8Z" />
        <path
          d="M10.6 9q-.5 5 4 5m-9 3q4-2 7 2m-5 7q2-5 7-3m.5 9q-3-3 0-6m14-17q.5 5-4 5m9 3q-4-2-7 2m5 7q-2-5-7-3m-.5 9q3-3 0-6"
          fill="none"
        />
      </g>
      <g className="brain-pixels" fill="#fff0ff">
        <rect x="9" y="11" width="2" height="2" />
        <rect x="14" y="6" width="1.5" height="1.5" />
        <rect x="24" y="10" width="2" height="2" />
        <rect x="29" y="16" width="1.5" height="1.5" />
        <rect x="10" y="23" width="2" height="2" />
        <rect x="16" y="28" width="1.5" height="1.5" />
        <rect x="25" y="25" width="2" height="2" />
      </g>
      <g
        className="brain-rays"
        fill="none"
        stroke="#d9b2f4"
        strokeWidth="1.2"
        strokeLinecap="round"
      >
        <path d="M20 0V-3M7 4 5 1M33 4l2-3M2 16l-3-1M38 16l3-1M3 29l-3 1M37 29l3 1M12 36l-1 3M28 36l1 3" />
      </g>
    </svg>
  );
}
export function Effort({
  value,
  change,
  supported,
}: {
  value: string;
  change: (v: string) => void;
  supported: boolean;
}) {
  return (
    <div className={"effort " + (value === "on" ? "thinking" : "")}>
      <div className="effort-title">
        <strong>Effort</strong>
        <span>
          {supported ? (value === "on" ? "On" : "Off") : "Unavailable"}
        </span>
        <span
          className="effort-help"
          title="The installed runtime supports thinking off/on. Four native effort levels are unavailable."
          aria-label="Thinking supports off and on"
        >
          ?
        </span>
      </div>
      <div className="effort-labels">
        <span>Faster</span>
        <span>Smarter</span>
      </div>
      <div className="effort-track">
        <input
          id="reasoning-effort"
          aria-label="Thinking"
          type="range"
          min="0"
          max="1"
          step="1"
          value={value === "on" ? 1 : 0}
          disabled={!supported}
          onChange={(event) =>
            change(event.target.value === "1" ? "on" : "off")
          }
          aria-valuetext={value === "on" ? "Thinking on" : "Thinking off"}
        />
        <div className="effort-fill" />
        <svg
          className="effort-field"
          viewBox="0 0 290 30"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {Array.from({ length: 84 }, (_, index) => (
            <rect
              key={index}
              x={32 + (index % 28) * 9}
              y={5 + Math.floor(index / 28) * 8}
              width={index % 4 === 0 ? 3 : 2}
              height={index % 4 === 0 ? 3 : 2}
              fill={index % 3 === 0 ? "#ffe9ff" : "#c98fea"}
            />
          ))}
        </svg>
        <span className="effort-tick tick-left" />
        <span className="effort-tick tick-right" />
        <span className="brain-thumb">
          <Brain on={value === "on"} />
        </span>
      </div>
      <p>Thinking {value === "on" ? "on" : "off"} · two supported states</p>
    </div>
  );
}
export function MetalButton({
  open,
  toggle,
}: {
  open: boolean;
  toggle: () => void;
}) {
  return (
    <button
      className="metal-button"
      id="plus-menu"
      type="button"
      aria-label="Add attachment or action"
      aria-expanded={open}
      aria-haspopup="menu"
      aria-controls={open ? "composer-actions" : undefined}
      onClick={toggle}
    >
      <span className="metal-rim" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="metal-face" aria-hidden="true">
        <svg viewBox="0 0 20 20">
          <path d="M10 5v10M5 10h10" />
        </svg>
      </span>
    </button>
  );
}
export function WorkingIndicator({ state }: { state: string }) {
  return (
    <span className="working-pixels" data-state={state} aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => (
        <i
          key={index}
          style={
            {
              "--pixel": index,
              "--pixel-x": [0, 4, 8, 4][index],
              "--pixel-y": [4, 0, 4, 8][index],
            } as CSSProperties
          }
        />
      ))}
    </span>
  );
}
