import type { Viewport } from "./overlay-placement";

/** Keep modal boundary Tab presses inside the app instead of browser chrome.
 * Nonmodal sheets retain the document's ordinary tab order. */
export function containModalTab(dialog: HTMLDialogElement,
  event: Pick<KeyboardEvent, "key" | "shiftKey" | "preventDefault">) {
  if (event.key !== "Tab" || !dialog.open || !dialog.matches(":modal")) return;
  const owner = dialog.ownerDocument;
  const targets = [...dialog.querySelectorAll<HTMLElement>("button,input,textarea,select,a[href],[tabindex]")]
    .filter(item => item.tabIndex >= 0 && !item.matches(":disabled") && !item.closest("[inert]")
      && item.getClientRects().length && owner.defaultView?.getComputedStyle(item).visibility !== "hidden");
  const index = targets.indexOf(owner.activeElement as HTMLElement);
  if (index < 0 || (event.shiftKey ? index === 0 : index === targets.length - 1)) {
    event.preventDefault();
    (event.shiftKey ? targets.at(-1) : targets[0])?.focus({ preventScroll: true });
  }
}

/** A sheet is useful only if it leaves room for both its content and composer.
 * These are Hermes layout thresholds, not measurements of the references. */
export function workspaceSurface(viewport: Viewport, headerBottom: number, composerTop: number) {
  const inset = 8;
  const width = Math.min(480, Math.max(0, viewport.width - inset * 2));
  const top = Math.max(viewport.top + inset, headerBottom + inset);
  const bottom = Math.min(viewport.top + viewport.height - inset, composerTop - inset);
  const height = Math.max(0, bottom - top);
  if (viewport.width > 640 && width >= 320 && height >= 240) {
    return { mode: "sheet" as const, left: viewport.left + viewport.width - inset - width,
      top, width, height };
  }
  const modalWidth = Math.min(600, Math.max(0, viewport.width - inset * 2));
  return { mode: "modal" as const, left: viewport.left + (viewport.width - modalWidth) / 2, top: viewport.top + inset,
    width: modalWidth, height: Math.max(0, viewport.height - inset * 2) };
}

/** Release the native top layer before an exit animation can retain its node.
 * A pointer dismissal must not steal the newly clicked outside control's focus. */
export function releaseSurface(dialog: HTMLDialogElement, trigger: HTMLElement | null,
  restore: boolean, owner: Document = document) {
  const active = owner.activeElement as HTMLElement | null;
  const outside = active?.isConnected && active !== owner.body && !dialog.contains(active) ? active : null;
  dialog.inert = true;
  if (dialog.open) dialog.close();
  if (outside) {
    if (owner.activeElement !== outside) outside.focus({ preventScroll: true });
    return;
  }
  if (!restore || owner.querySelector("dialog[open]")) return;
  const target = [trigger, owner.getElementById("new-session"), owner.getElementById("prompt")]
    .find(item => item?.isConnected && item.getClientRects().length && !item.closest("[inert]"));
  target?.focus({ preventScroll: true });
}
