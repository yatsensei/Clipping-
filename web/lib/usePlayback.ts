"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { indexAtTime, lapTiming } from "./track";
import type { Strategy } from "./api";

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Subscribes to the OS motion preference.
 *
 * useSyncExternalStore rather than an effect: matchMedia IS an external store, and
 * reading it in an effect means rendering once with the wrong answer and then again with
 * the right one. Nothing here autoplays, so honouring the preference means never
 * starting motion on its own — pressing Play is still an explicit request and is obeyed.
 */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia(MOTION_QUERY);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia(MOTION_QUERY).matches,
    () => false, // server render: assume motion is allowed, corrected on hydration
  );
}

/**
 * Drives the car marker in simulated lap time.
 *
 * One requestAnimationFrame loop advances a clock; position is derived from that clock,
 * never from a frame counter. Stepping per data point would move the car a fixed 5 m per
 * frame — fast through hairpins and slow down straights, precisely inverted.
 *
 * Only `elapsed` is state. The grid index is DERIVED during render rather than stored,
 * so a frame is one state update rather than two. An earlier version called setIndex
 * inside the setElapsed updater, which is a side effect in a reducer and runs twice
 * under StrictMode.
 *
 * The loop stops when the tab is hidden, and never autoplays under
 * prefers-reduced-motion. The scrub bar still works there, so the content is fully
 * reachable with no animation at all.
 */
export function usePlayback(strategy: Strategy | null, stepM: number) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [elapsed, setElapsed] = useState(0);
  const reducedMotion = useReducedMotion();

  const timing = useMemo(
    () => (strategy ? lapTiming(strategy, stepM) : null),
    [strategy, stepM],
  );

  // Reset the clock when the lap changes, adjusting state during render rather than in
  // an effect — the effect version fires an extra render pass every time.
  const [seenTiming, setSeenTiming] = useState(timing);
  if (timing !== seenTiming) {
    setSeenTiming(timing);
    setElapsed(0);
  }

  const frame = useRef<number | null>(null);
  const last = useRef(0);

  // `speed` is a dependency rather than a ref, so changing it restarts the loop. That
  // costs one cancelled frame on a button press and keeps the effect honest about what
  // it reads.
  useEffect(() => {
    if (!playing || !timing) return;

    const tick = (now: number) => {
      const dt = last.current ? (now - last.current) / 1000 : 0;
      last.current = now;
      setElapsed((prev) => (prev + dt * speed) % timing.total);
      frame.current = requestAnimationFrame(tick);
    };

    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
      last.current = 0;
    };
  }, [playing, timing, speed]);

  // Never burn frames on a tab nobody is looking at.
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) setPlaying(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const scrubTo = useCallback(
    (fraction: number) => {
      if (!timing) return;
      setElapsed(Math.max(0, Math.min(1, fraction)) * timing.total);
    },
    [timing],
  );

  const toggle = useCallback(() => setPlaying((p) => !p), []);
  const restart = useCallback(() => setElapsed(0), []);

  const index = timing ? indexAtTime(timing.cumulative, elapsed) : 0;
  const total = timing?.total ?? 0;

  return {
    index,
    elapsed,
    total,
    playing,
    speed,
    setSpeed,
    toggle,
    restart,
    scrubTo,
    prefersReducedMotion: reducedMotion,
  };
}
