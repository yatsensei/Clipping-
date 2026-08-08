"use client";

import { useSyncExternalStore } from "react";

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Subscribes to the OS motion preference.
 *
 * useSyncExternalStore rather than an effect: matchMedia IS an external store, and
 * reading it in an effect means rendering once with the wrong answer and then again with
 * the right one — which for the landing page would mean briefly binding the track
 * animation to the scrollbar for a reader who asked for no motion.
 *
 * The server snapshot assumes motion is allowed and is corrected on hydration. Nothing
 * in this app autoplays, so the worst case is a still frame.
 */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia(MOTION_QUERY);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia(MOTION_QUERY).matches,
    () => false,
  );
}
