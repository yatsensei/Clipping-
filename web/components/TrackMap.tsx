"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Geometry, Strategy } from "@/lib/api";
import { TOKENS, colourFor, project, strokeFor } from "@/lib/track";

/**
 * The track, drawn from real GPS and coloured by what the power unit is doing.
 *
 * Drawn as many short segments rather than one path, because the colour changes along
 * its length. Segments are batched: adjacent points sharing a visual state become one
 * <path>, which takes a 1,100-point lap from 1,100 nodes to typically under 80.
 *
 * Two things are sized in SCREEN PIXELS rather than viewBox units — the telemetry card
 * and the car — because the viewBox scale depends on the circuit's shape. Sized in
 * viewBox units, the card's labels came out at 5 px on a tall circuit like Monza, and
 * the car was an 8 px smudge. The card is therefore an HTML overlay and the car carries
 * a counter-scale, so both stay legible whatever the track looks like.
 */

const CARD_W = 176;
const CARD_H = 92;
const CAR_PX = 30; // rendered length of the car glyph
const GLYPH_LEN = 28; // its length in viewBox units before counter-scaling

interface Box {
  w: number;
  h: number;
}

export function TrackMap({
  geometry,
  strategy,
  carIndex,
  socCapacityMj,
  showCorners = true,
}: {
  geometry: Geometry;
  strategy: Strategy;
  carIndex: number;
  socCapacityMj: number;
  showCorners?: boolean;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box>({ w: 0, h: 0 });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    // Measure once immediately. Waiting for the observer's first callback leaves the
    // telemetry card unrendered until something happens to resize the page, and a
    // ResizeObserver does not necessarily fire on a tab that is not compositing.
    const measure = () => {
      const { width, height } = host.getBoundingClientRect();
      setBox((prev) =>
        prev.w === width && prev.h === height ? prev : { w: width, h: height },
      );
    };
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  // No horizontal reserve: the panel's HEIGHT is what limits the track, so padding the
  // viewBox sideways only adds letterbox without making the map any bigger.
  const projection = useMemo(() => project(geometry, 1000, 40), [geometry]);

  // preserveAspectRatio="xMidYMid meet" in explicit form, so the overlay can be placed
  // in the same coordinate space the SVG is actually using.
  const view = useMemo(() => {
    const scale =
      box.w > 0 && box.h > 0
        ? Math.min(box.w / projection.width, box.h / projection.height)
        : 0;
    return {
      scale,
      ox: (box.w - projection.width * scale) / 2,
      oy: (box.h - projection.height * scale) / 2,
    };
  }, [box, projection]);

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

  // Position and heading. Heading comes from a short chord rather than the adjacent
  // sample, which is only 5 m away and makes the car's angle jitter on straights.
  const car = useMemo(() => {
    const { points } = projection;
    const n = points.length;
    const i0 = Math.floor(carIndex) % n;
    const i1 = (i0 + 1) % n;
    const f = carIndex - Math.floor(carIndex);
    const x = points[i0].x * (1 - f) + points[i1].x * f;
    const y = points[i0].y * (1 - f) + points[i1].y * f;

    const span = 4;
    const back = points[(i0 - span + n) % n];
    const ahead = points[(i0 + span) % n];
    const angle = (Math.atan2(ahead.y - back.y, ahead.x - back.x) * 180) / Math.PI;
    return { x, y, angle };
  }, [projection, carIndex]);

  const cornerMarks = useMemo(() => {
    if (!showCorners) return [];
    const step = geometry.step_m;
    return geometry.official_corners.map((c) => {
      const idx = Math.round(c.distance_m / step) % projection.points.length;
      return { ...c, ...projection.points[idx] };
    });
  }, [geometry, projection, showCorners]);

  const i = Math.floor(carIndex) % strategy.clipping.length;
  const clipping = strategy.clipping[i];
  const harvesting = strategy.harvest_kw[i] > 1;
  const deploying = strategy.deploy_kw[i] > 1;
  const speed = strategy.speed_kph[i];
  const socMj = strategy.soc_mj[i];
  const socPct = Math.max(0, Math.min(100, (socMj / socCapacityMj) * 100));

  const state = clipping
    ? { label: "CLIPPING", colour: TOKENS.clip, detail: "no power left" }
    : harvesting
      ? {
          label: "HARVESTING",
          colour: TOKENS.harvest,
          detail: `${strategy.harvest_kw[i].toFixed(0)} kW in`,
        }
      : deploying
        ? {
            label: "DEPLOYING",
            colour: TOKENS.deploy,
            detail: `${strategy.deploy_kw[i].toFixed(0)} kW out`,
          }
        : { label: "COASTING", colour: TOKENS.muted, detail: "no request" };

  // Card placement, in screen pixels, on whichever side of the car has more room.
  const carPx = {
    x: view.ox + car.x * view.scale,
    y: view.oy + car.y * view.scale,
  };
  const flip = carPx.x > box.w * 0.5;
  const gap = 34;
  const cardLeft = Math.max(
    6,
    Math.min(
      box.w - CARD_W - 6,
      flip ? carPx.x - gap - CARD_W : carPx.x + gap,
    ),
  );
  const cardTop = Math.max(
    6,
    Math.min(box.h - CARD_H - 6, carPx.y - CARD_H / 2),
  );

  // Where the leader line meets the card, converted back into viewBox space.
  const anchorPx = {
    x: flip ? cardLeft + CARD_W : cardLeft,
    y: cardTop + CARD_H / 2,
  };
  const anchor =
    view.scale > 0
      ? {
          x: (anchorPx.x - view.ox) / view.scale,
          y: (anchorPx.y - view.oy) / view.scale,
        }
      : car;

  // Counter-scale so the glyph renders at a constant size on every circuit.
  const carScale = view.scale > 0 ? CAR_PX / (GLYPH_LEN * view.scale) : 1;

  const batteryColour =
    socPct < 12 ? TOKENS.clip : socPct < 35 ? "#FF8A3D" : TOKENS.harvest;
  const cells = 5;
  const filled = Math.round((socPct / 100) * cells);

  return (
    <div ref={hostRef} className="relative h-full w-full">
      <svg
        viewBox={`0 0 ${projection.width} ${projection.height}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label={
          `Track map of ${geometry.circuit_id}, coloured by electrical deployment. ` +
          `Car at ${speed.toFixed(0)} kilometres per hour, battery ` +
          `${socPct.toFixed(0)} per cent, ${state.label.toLowerCase()}.`
        }
      >
        <defs>
          <filter id="car-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="2" result="blur" />
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

        {batches.map((b, k) => (
          <path
            key={k}
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
            <circle cx={c.x} cy={c.y} r={2} fill={TOKENS.muted} opacity={0.7} />
            <text
              x={c.x}
              y={c.y - 8}
              fill={TOKENS.muted}
              fontSize={11}
              textAnchor="middle"
              className="tabular select-none"
            >
              {c.number}
              {c.letter}
            </text>
          </g>
        ))}

        {view.scale > 0 && (
          <line
            x1={car.x}
            y1={car.y}
            x2={anchor.x}
            y2={anchor.y}
            stroke={state.colour}
            strokeWidth={1.5 / view.scale}
            opacity={0.55}
            strokeDasharray={`${4 / view.scale} ${4 / view.scale}`}
          />
        )}

        <g
          transform={`translate(${car.x.toFixed(2)},${car.y.toFixed(2)}) rotate(${car.angle.toFixed(1)}) scale(${carScale.toFixed(3)})`}
        >
          <CarGlyph colour={state.colour} />
        </g>
      </svg>

      {/* Telemetry card: HTML, so its type stays crisp and fixed-size. */}
      {box.w > 0 && (
        <div
          className="pointer-events-none absolute rounded-md border bg-[#141619]/95 px-3 py-2 shadow-lg backdrop-blur-sm"
          style={{
            left: cardLeft,
            top: cardTop,
            width: CARD_W,
            height: CARD_H,
            borderColor: `${state.colour}88`,
          }}
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[8px] uppercase tracking-[0.18em] text-[#6B7280]">
                Speed
              </div>
              <div className="tabular -mt-0.5 text-[22px] leading-none text-[#F2F0EB]">
                {speed.toFixed(0)}
                <span className="ml-1 text-[9px] text-[#6B7280]">km/h</span>
              </div>
            </div>
            <span
              className="rounded px-1.5 py-0.5 text-[8px] font-medium tracking-[0.1em]"
              style={{
                color: state.colour,
                backgroundColor: `${state.colour}26`,
                border: `1px solid ${state.colour}66`,
              }}
            >
              {state.label}
            </span>
          </div>

          <div className="mt-2 flex items-center gap-2">
            {/* Mini battery: five cells plus a terminal nub. */}
            <span className="flex items-center" aria-hidden="true">
              <span className="flex h-[13px] w-[30px] items-center gap-[1.5px] rounded-[2px] border border-[#6B7280] px-[1.5px]">
                {Array.from({ length: cells }, (_, k) => (
                  <span
                    key={k}
                    className="h-[8px] flex-1 rounded-[1px]"
                    style={{
                      backgroundColor: k < filled ? batteryColour : TOKENS.line,
                    }}
                  />
                ))}
              </span>
              <span className="h-[6px] w-[2px] rounded-r-sm bg-[#6B7280]" />
            </span>
            <span className="tabular text-[13px] leading-none text-[#F2F0EB]">
              {socPct.toFixed(0)}%
            </span>
            <span className="tabular text-[9px] leading-none text-[#6B7280]">
              {socMj.toFixed(2)} MJ
            </span>
          </div>

          <div className="mt-1.5 text-[9px] leading-none text-[#6B7280]">
            {state.detail}
          </div>
        </div>
      )}
    </div>
  );
}

/** Top-down single-seater: nose, wings, sidepods and four wheels, pointing along +x. */
function CarGlyph({ colour }: { colour: string }) {
  return (
    <g filter="url(#car-glow)">
      <path
        d="M -11 -2.6 L 3 -2.6 L 12 -1.5 L 14 0 L 12 1.5 L 3 2.6 L -11 2.6 Z"
        fill={colour}
        stroke={TOKENS.void}
        strokeWidth={0.5}
      />
      <rect x={-13.5} y={-5} width={2.6} height={10} rx={0.8} fill={colour} />
      <rect x={11.5} y={-4} width={2.2} height={8} rx={0.8} fill={colour} />
      {[
        [-7.5, -4.6],
        [-7.5, 4.6],
        [6, -4.2],
        [6, 4.2],
      ].map(([wx, wy], k) => (
        <rect
          key={k}
          x={wx - 2.2}
          y={wy - 1.5}
          width={4.4}
          height={3}
          rx={1}
          fill={TOKENS.bone}
          opacity={0.92}
        />
      ))}
    </g>
  );
}
