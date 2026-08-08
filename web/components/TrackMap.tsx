"use client";

import { useMemo } from "react";
import type { Geometry, Strategy } from "@/lib/api";
import { TOKENS, colourFor, project, strokeFor } from "@/lib/track";

/**
 * The track, drawn from real GPS and coloured by what the power unit is doing.
 *
 * Drawn as many short segments rather than one path, because the colour changes along
 * its length. Segments are batched: adjacent points sharing a visual state become one
 * <path>, which takes a 1,100-point lap from 1,100 nodes to typically under 80 and keeps
 * re-renders cheap.
 */
export function TrackMap({
  geometry,
  strategy,
  carIndex,
  showCorners = true,
}: {
  geometry: Geometry;
  strategy: Strategy;
  carIndex: number;
  showCorners?: boolean;
}) {
  const projection = useMemo(() => project(geometry), [geometry]);

  const batches = useMemo(() => {
    const { points } = projection;
    const out: { d: string; colour: string; width: number }[] = [];
    let current: string[] = [];
    let colour = "";
    let width = 0;

    const flush = () => {
      if (current.length > 1) out.push({ d: current.join(" "), colour, width });
    };

    for (let i = 0; i < points.length; i++) {
      const c = colourFor(
        strategy.deploy_kw[i],
        strategy.harvest_kw[i],
        strategy.clipping[i],
      );
      const w = strokeFor(
        strategy.deploy_kw[i],
        strategy.harvest_kw[i],
        strategy.clipping[i],
      );
      if (c !== colour || w !== width) {
        flush();
        current = [`M${points[i].x.toFixed(2)},${points[i].y.toFixed(2)}`];
        colour = c;
        width = w;
      }
      const next = points[(i + 1) % points.length];
      current.push(`L${next.x.toFixed(2)},${next.y.toFixed(2)}`);
    }
    flush();
    return out;
  }, [projection, strategy]);

  const car = useMemo(() => {
    const { points } = projection;
    const n = points.length;
    const i0 = Math.floor(carIndex) % n;
    const i1 = (i0 + 1) % n;
    const f = carIndex - Math.floor(carIndex);
    return {
      x: points[i0].x * (1 - f) + points[i1].x * f,
      y: points[i0].y * (1 - f) + points[i1].y * f,
    };
  }, [projection, carIndex]);

  const cornerMarks = useMemo(() => {
    if (!showCorners) return [];
    const step = geometry.step_m;
    return geometry.official_corners.map((c) => {
      const idx = Math.round(c.distance_m / step) % projection.points.length;
      return { ...c, ...projection.points[idx] };
    });
  }, [geometry, projection, showCorners]);

  const clippingNow = strategy.clipping[Math.floor(carIndex) % strategy.clipping.length];

  return (
    <svg
      viewBox={`0 0 ${projection.width} ${projection.height}`}
      className="w-full h-auto"
      role="img"
      aria-label={`Track map of ${geometry.circuit_id}, coloured by electrical deployment`}
    >
      <defs>
        {/* Non-colour encoding for clipping, so it survives a colour-blind palette. */}
        <pattern id="clip-hatch" width="6" height="6" patternUnits="userSpaceOnUse"
                 patternTransform="rotate(45)">
          <rect width="6" height="6" fill={TOKENS.clip} opacity="0.25" />
          <line x1="0" y1="0" x2="0" y2="6" stroke={TOKENS.clip} strokeWidth="2" />
        </pattern>
        <filter id="car-glow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Ghost outline so the whole lap stays readable where nothing is happening. */}
      <path
        d={projection.path}
        fill="none"
        stroke={TOKENS.line}
        strokeWidth={9}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.55}
      />

      {batches.map((b, i) => (
        <path
          key={i}
          d={b.d}
          fill="none"
          stroke={b.colour}
          strokeWidth={b.width}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}

      {cornerMarks.map((c) => (
        <g key={`${c.number}${c.letter}`}>
          <circle cx={c.x} cy={c.y} r={2} fill={TOKENS.muted} opacity={0.8} />
          <text
            x={c.x}
            y={c.y - 7}
            fill={TOKENS.muted}
            fontSize={9}
            textAnchor="middle"
            className="tabular select-none"
          >
            {c.number}
            {c.letter}
          </text>
        </g>
      ))}

      <circle
        cx={car.x}
        cy={car.y}
        r={9}
        fill="none"
        stroke={clippingNow ? TOKENS.clip : TOKENS.bone}
        strokeWidth={1.5}
        opacity={0.65}
      />
      <circle
        cx={car.x}
        cy={car.y}
        r={4.5}
        fill={clippingNow ? TOKENS.clip : TOKENS.bone}
        filter="url(#car-glow)"
      />
    </svg>
  );
}
