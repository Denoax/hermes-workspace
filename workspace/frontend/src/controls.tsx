import { useEffect, useRef, type ReactNode } from "react";
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
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const dialog = ref.current!;
    dialog.show();
    const resize = () => {
      if (innerWidth < 500) dialog.style.maxHeight = "calc(100dvh - 80px)";
    };
    const outside = (e: PointerEvent) => {
      const target = e.target as HTMLElement;
      if (!dialog.contains(target) && !target.closest(".toolbar-actions"))
        close();
    };
    const escape = (e: KeyboardEvent) => {
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
      before?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
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
    </dialog>
  );
}
export function Brain({ on }: { on: boolean }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden="true"
    >
      <path d="M15 7c-1-5-8-4-8 1-5 0-6 7-3 9-3 5 1 10 6 9 2 5 5 2 5-1V7Zm2 0c1-5 8-4 8 1 5 0 6 7 3 9 3 5-1 10-6 9-2 5-5 2-5-1V7Z" />
      <path
        d={
          on
            ? "M7 8q1 6 5 3M4 17q4-3 7 1M7 25q-1-4 4-4M25 8q-1 6-5 3M28 17q-4-3-7 1M25 25q1-4-4-4"
            : "M7 15h4m10 0h4"
        }
      />
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
        <button
          type="button"
          aria-label="About thinking effort"
          title="This installed runtime supports a verified on/off template switch, not four native effort levels."
        >
          ?
        </button>
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
          onChange={(e) => change(e.target.value === "1" ? "on" : "off")}
          aria-valuetext={value === "on" ? "Thinking on" : "Thinking off"}
        />
        <div className="effort-fill" />
        <span className="brain-thumb">
          <Brain on={value === "on"} />
        </span>
        <i />
        <i />
      </div>
      <p>
        {supported
          ? "Verified thinking on/off"
          : "The installed model has no verified effort control."}
      </p>
    </div>
  );
}
