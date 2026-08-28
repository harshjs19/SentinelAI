import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";

export function usePointerSpotlight<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const frame = useRef<number | null>(null);

  useEffect(() => () => {
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
  }, []);

  const onPointerMove = (event: ReactPointerEvent<T>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const target = event.currentTarget;
    const clientX = event.clientX;
    const clientY = event.clientY;
    if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    frame.current = window.requestAnimationFrame(() => {
      const bounds = target.getBoundingClientRect();
      target.style.setProperty("--spot-x", `${clientX - bounds.left}px`);
      target.style.setProperty("--spot-y", `${clientY - bounds.top}px`);
    });
  };

  return { ref, onPointerMove };
}
