import { useLayoutEffect, useRef, useState } from "react";

/** Follow growth only while the reader stays near the end. No running loop. */
export function useReadingPosition(scope: string, conversation = true) {
  const container = useRef<HTMLElement>(null);
  const follow = useRef(true);
  const [atEnd, setAtEnd] = useState(true);
  const jump = () => {
    follow.current = true;
    setAtEnd(true);
    const node = container.current;
    if (node) node.scrollTop = node.scrollHeight - node.clientHeight;
  };
  useLayoutEffect(() => {
    const node = container.current;
    if (!node) return;
    let frame = 0;
    let live = true;
    follow.current = conversation;
    setAtEnd(true);
    node.scrollTop = conversation ? node.scrollHeight - node.clientHeight : 0;
    const read = () => {
      const near = node.scrollHeight - node.clientHeight - node.scrollTop <= 64;
      follow.current = conversation && near;
      setAtEnd(!conversation || near);
    };
    const schedule = () => {
      if (!live || !conversation || document.hidden || frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (live && !document.hidden && follow.current) node.scrollTop = node.scrollHeight - node.clientHeight;
      });
    };
    const visibility = () => {
      if (document.hidden) {
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
      } else schedule();
    };
    const resize = new ResizeObserver(schedule);
    const column = node.firstElementChild;
    if (column) resize.observe(column);
    resize.observe(node);
    node.addEventListener("scroll", read, { passive: true });
    document.addEventListener("visibilitychange", visibility);
    return () => {
      live = false;
      resize.disconnect();
      if (frame) cancelAnimationFrame(frame);
      node.removeEventListener("scroll", read);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [scope, conversation]);
  return { container, atEnd, jump };
}
