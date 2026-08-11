"use client";

import { useEffect, useRef } from "react";
import { TOKENS } from "@/lib/track";
import type { FieldState } from "./ShaderBackground";

/**
 * A side-profile 2026-specification car sitting behind the landing narrative, driven by
 * the same energy state as the shader.
 *
 * It is a readout, not an ornament — the same justification the background field has:
 *
 *   energy store   the six cells along the floor drain and refill with state of charge
 *   power flow     the halo and rear light glow red under deployment, cyan when
 *                  harvesting, and desaturate to grey while clipping
 *   speed          the wheels spin at a rate set by the car's actual speed, and the
 *                  motion streaks lengthen with it
 *
 * Everything per-frame is written straight to the DOM through refs. Re-rendering React
 * sixty times a second to move a wheel would be the one thing guaranteed to blow the
 * frame budget the brief sets.
 *
 * Proportions follow the 2026 regulations rather than a generic wedge: narrower body,
 * reduced wheelbase, and the simpler front wing the rules mandate.
 */
/**
 * The car's own palette, mixed from the page's ink toward its surface.
 *
 * Not the panel/line tokens: those are near-black on the dark theme, and a near-black car
 * on a near-black page at low opacity composites to a 5/255 difference — which is to say,
 * invisible. Mixing ink into surface instead gives a silhouette that is a definite step
 * away from the background in BOTH themes, lightening on dark and darkening on light.
 */
const SHELL = "color-mix(in srgb, var(--ink) 30%, var(--surface))";
const SHELL_DEEP = "color-mix(in srgb, var(--ink) 17%, var(--surface))";
const TRIM = "color-mix(in srgb, var(--ink) 48%, var(--surface))";
const DIM_CELL = "color-mix(in srgb, var(--ink) 22%, var(--surface))";

export function CarSilhouette({
  state,
  progress,
}: {
  state: React.RefObject<FieldState>;
  progress: React.RefObject<number>;
}) {
  const rootRef = useRef<SVGSVGElement>(null);
  const frontWheelRef = useRef<SVGGElement>(null);
  const rearWheelRef = useRef<SVGGElement>(null);
  const glowRef = useRef<SVGGElement>(null);
  const streakRef = useRef<SVGGElement>(null);
  const cellsRef = useRef<(SVGRectElement | null)[]>([]);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame: number | null = null;
    let spin = 0;
    let last = 0;

    const paint = (now: number) => {
      const dt = last ? Math.min((now - last) / 1000, 0.1) : 0;
      last = now;

      const s = state.current ?? { soc: 1, deploy: 0, clip: 0 };
      const p = progress.current ?? 0;

      // Speed is not in FieldState, so it is inferred from what is: deployment implies
      // the car is driving hard, clipping implies flat out with nothing left.
      const pace = Math.min(1, 0.35 + s.deploy * 0.5 + s.clip * 0.45);

      if (!reduced) {
        spin += dt * pace * 900;
        const wheels = `rotate(${spin.toFixed(1)})`;
        frontWheelRef.current?.setAttribute("transform", wheels);
        rearWheelRef.current?.setAttribute("transform", wheels);
        streakRef.current?.setAttribute(
          "style",
          `opacity:${(0.15 + pace * 0.5).toFixed(2)};transform:scaleX(${(0.6 + pace * 0.9).toFixed(2)})`,
        );
      }

      // Colour of the energy flow: red deploying, cyan harvesting, grey clipping.
      const colour =
        s.clip > 0.5
          ? TOKENS.clip
          : s.deploy > 0.02
            ? TOKENS.deploy
            : TOKENS.harvest;
      glowRef.current?.setAttribute("stroke", colour);
      glowRef.current?.setAttribute(
        "style",
        `opacity:${(0.25 + s.deploy * 0.6 + (1 - s.clip) * 0.1).toFixed(2)}`,
      );

      // Energy store: six cells, filled from the front.
      const filled = Math.round(s.soc * 6);
      cellsRef.current.forEach((cell, i) => {
        if (!cell) return;
        cell.setAttribute("fill", i < filled ? colour : DIM_CELL);
        cell.setAttribute("opacity", i < filled ? "1" : "0.5");
      });

      // Drifts gently across the viewport as the lap progresses, so the car is not
      // pinned to one spot for the whole story.
      rootRef.current?.style.setProperty(
        "transform",
        `translate3d(${(-6 + p * 12).toFixed(2)}%, 0, 0)`,
      );

      frame = reduced ? null : requestAnimationFrame(paint);
    };

    paint(performance.now());
    if (reduced) return;

    const onVisibility = () => {
      if (document.hidden && frame !== null) {
        cancelAnimationFrame(frame);
        frame = null;
        last = 0;
      } else if (!document.hidden && frame === null) {
        frame = requestAnimationFrame(paint);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [state, progress]);

  return (
    <div
      // Sat low rather than centred: at the vertical middle the energy strip lands
      // directly behind the narrative paragraph, and a row of lit red cells under body
      // text is the one place this must not compete for attention.
      className="pointer-events-none fixed inset-0 -z-[5] flex items-end justify-center overflow-hidden pb-[7vh]"
      aria-hidden="true"
    >
      <svg
        ref={rootRef}
        viewBox="0 0 760 250"
        className="w-[190%] max-w-none opacity-50 sm:w-[130%] lg:w-[105%]"
        style={{ willChange: "transform" }}
      >
        {/* Motion streaks behind the car. */}
        <g ref={streakRef} style={{ transformOrigin: "120px 150px" }}>
          {[104, 126, 148, 170].map((y, i) => (
            <rect
              key={y}
              x={10 - i * 6}
              y={y}
              width={70 + i * 18}
              height={2.5}
              rx={1.25}
              fill={TOKENS.deploy}
              opacity={0.5 - i * 0.08}
            />
          ))}
        </g>

        {/* Floor and diffuser. */}
        <path
          d="M96 176 L640 176 L664 168 L668 156 L648 152 L120 152 Z"
          fill={SHELL_DEEP}
        />

        {/* Sidepod and engine cover, sweeping to the rear. */}
        <path
          d="M250 152 C300 150 330 140 356 126 C392 106 428 100 470 100 C520 100 566 112 596 128 L616 152 Z"
          fill={SHELL}
        />
        {/* Nose and front wing. */}
        <path d="M96 168 L104 150 L150 144 L214 140 L250 152 Z" fill={SHELL} />
        <path d="M74 176 L150 176 L150 166 L78 166 Z" fill={TRIM} />
        {/* Rear wing, simplified per the 2026 movable-aero rules. */}
        <path d="M604 96 L692 96 L692 106 L604 106 Z" fill={TRIM} />
        <path d="M646 106 L660 106 L660 150 L646 150 Z" fill={SHELL_DEEP} />

        {/* Cockpit and halo — the halo carries the power-flow colour. */}
        <path
          d="M356 126 C372 112 396 106 420 106 L446 106 L440 126 Z"
          fill={SHELL_DEEP}
        />
        <g ref={glowRef} stroke={TOKENS.deploy} fill="none" strokeWidth={5} strokeLinecap="round">
          <path d="M352 124 C372 92 424 84 462 96" />
          <path d="M404 92 L404 108" strokeWidth={3} />
          {/* Rear light. */}
          <path d="M664 138 L664 148" strokeWidth={6} />
        </g>

        {/* Energy store: six cells along the floor. */}
        <g>
          <rect
            x={286}
            y={156}
            width={188}
            height={16}
            rx={3}
            fill="none"
            stroke={TRIM}
            strokeWidth={1.5}
          />
          {Array.from({ length: 6 }, (_, i) => (
            <rect
              key={i}
              ref={(el) => {
                cellsRef.current[i] = el;
              }}
              x={291 + i * 30}
              y={160}
              width={25}
              height={8}
              rx={1.5}
              fill={DIM_CELL}
            />
          ))}
        </g>

        {/* Wheels. Spokes make the rotation legible. */}
        <Wheel cx={168} cy={168} r={46} innerRef={frontWheelRef} />
        <Wheel cx={598} cy={168} r={52} innerRef={rearWheelRef} />
      </svg>
    </div>
  );
}

function Wheel({
  cx,
  cy,
  r,
  innerRef,
}: {
  cx: number;
  cy: number;
  r: number;
  innerRef: React.RefObject<SVGGElement | null>;
}) {
  return (
    <g transform={`translate(${cx},${cy})`}>
      <circle r={r} fill={SHELL_DEEP} />
      <circle r={r} fill="none" stroke={TRIM} strokeWidth={3} />
      <circle r={r * 0.42} fill={SHELL} />
      <g ref={innerRef}>
        {[0, 60, 120, 180, 240, 300].map((angle) => (
          <rect
            key={angle}
            x={-1.5}
            y={-r * 0.4}
            width={3}
            height={r * 0.8}
            rx={1.5}
            fill={TRIM}
            transform={`rotate(${angle})`}
          />
        ))}
      </g>
    </g>
  );
}
