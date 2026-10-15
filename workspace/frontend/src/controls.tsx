import { useEffect, useRef, type ReactNode, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { motion, useIsPresent } from "motion/react";
import { useReducedMotion } from "./lib/reduced-motion";
export function Panel({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const present = useIsPresent();
  const presentRef = useRef(present);
  presentRef.current = present;
  const reduced = useReducedMotion();
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const trigger =
      document.getElementById(title.toLowerCase() + "-toggle") ?? before;
    const dialog = ref.current!;
    dialog.show();
    const resize = () => {
      dialog.style.maxHeight = innerWidth < 500 ? "calc(100dvh - 80px)" : "";
    };
    const outside = (e: PointerEvent) => {
      if (!presentRef.current) return;
      const target = e.target as HTMLElement;
      if (!dialog.contains(target) && !target.closest(".toolbar-actions"))
        close();
    };
    const escape = (e: KeyboardEvent) => {
      if (!presentRef.current) return;
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    resize();
    addEventListener("resize", resize);
    addEventListener("pointerdown", outside);
    addEventListener("keydown", escape);
    return () => {
      dialog.close();
      removeEventListener("resize", resize);
      removeEventListener("pointerdown", outside);
      removeEventListener("keydown", escape);
      if (!document.querySelector('dialog[open]:not([aria-hidden="true"])'))
        trigger?.focus();
    };
  }, [title]);
  return createPortal(
    <motion.dialog
      ref={ref}
      initial={{ opacity: 0, y: reduced ? 0 : -10, scale: reduced ? 1 : 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: reduced ? 0 : -8, scale: reduced ? 1 : 0.97 }}
      transition={{ duration: reduced ? 0 : 0.23, ease: [0.2, 0.8, 0.2, 1] }}
      style={{
        transformOrigin: "top right",
        pointerEvents: present ? "auto" : "none",
      }}
      aria-hidden={!present}
      aria-label={title}
      className="panel"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            close();
        }
      }}
    >
      <header>
        <h2>{title}</h2>
        <button
          className="icon-button"
          data-action="close-dialog"
          aria-label={"Close " + title}
          onClick={close}
        >
          ×
        </button>
      </header>
      {children}
    </motion.dialog>,
    document.body,
  );
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
