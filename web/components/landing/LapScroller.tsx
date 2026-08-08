"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Geometry, Strategy } from "@/lib/api";
import { TOKENS, project } from "@/lib/track";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { activeBeatForScroll, buildBeats, lapFractionForScroll } from "./beats";
import { ShaderBackground, type FieldState } from "./ShaderBackground";

/**
 * The signature: scroll position IS lap distance.
 *
 * The track is pinned with CSS `position: sticky` rather than a scroll library. The brief
 * allows GSAP ScrollTrigger for the pinned sequence "where hand-rolling is genuinely
 * worse" — it is not worse here. Sticky is one line, needs no JS to hold the pin, cannot
 * desync from the scrollbar, and survives resize for free.
 *
 * Per frame the loop writes directly to the DOM through refs: stroke-dashoffset on the
 * path, a transform on the car, and uniforms on the shader. React state changes only when
 * the ACTIVE BEAT changes, so scrolling the page does not re-render the component tree.
 * The scroll listener is passive and only raises a flag; all reads happen inside
 * requestAnimationFrame.
 */
export function LapScroller({
  geometry,
  greedy,
}: {
  geometry: Geometry;
  greedy: Strategy;
}) {
  const beats = useMemo(
    () => buildBeats(greedy, geometry.lap_distance_m),
    [greedy, geometry.lap_distance_m],
  );
  const projection = useMemo(() => project(geometry, 1000, 60), [geometry]);

  const containerRef = useRef<HTMLDivElement>(null);
  const pathRef = useRef<SVGPathElement>(null);
  const carRef = useRef<SVGGElement>(null);
  const readoutRef = useRef<HTMLDivElement>(null);
  const field = useRef<FieldState>({ soc: 1, deploy: 0, clip: 0 });

  const [activeBeat, setActiveBeat] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    const container = containerRef.current;
    const path = pathRef.current;
    if (!container || !path) return;

    // With reduced motion the lap is simply shown complete and the story is read as
    // static sections. Nothing below binds to the scrollbar.
    if (reduced) {
      path.style.strokeDasharray = "none";
      path.style.strokeDashoffset = "0";
      field.current = { soc: 0.35, deploy: 0.2, clip: 0.4 };
      return;
    }

    const total = path.getTotalLength();
    path.style.strokeDasharray = `${total}`;
    path.style.strokeDashoffset = `${total}`;

    const n = greedy.speed_kph.length;
    const knots = beats.map((b) => b.at);
    let queued = false;
    let lastBeat = -1;


    const update = () => {
      queued = false;
      const rect = container.getBoundingClientRect();
      const scrollable = rect.height - window.innerHeight;
      const progress =
        scrollable > 0 ? Math.min(Math.max(-rect.top / scrollable, 0), 1) : 0;

      const lap = lapFractionForScroll(progress, knots);

      // Draw the outline in step with distance travelled.
      path.style.strokeDashoffset = `${total * (1 - lap)}`;

      const point = path.getPointAtLength(total * lap);
      if (carRef.current) {
        carRef.current.setAttribute(
          "transform",
          `translate(${point.x.toFixed(2)},${point.y.toFixed(2)})`,
        );
      }

      const i = Math.min(n - 1, Math.round(lap * (n - 1)));
      const socMj = greedy.soc_mj[i];
      const clipping = greedy.clipping[i];
      field.current = {
        soc: Math.min(Math.max(socMj / Math.max(greedy.soc_start_mj, 0.001), 0), 1),
        deploy: Math.min(greedy.deploy_kw[i] / 350, 1),
        clip: clipping ? 1 : 0,
      };

      if (readoutRef.current) {
        readoutRef.current.textContent =
          `${greedy.speed_kph[i].toFixed(0)} km/h · ${socMj.toFixed(2)} MJ` +
          (clipping ? " · CLIPPING" : "");
      }

      // Each beat owns an equal slice of scroll, so the active one follows the section
      // the reader is actually looking at. Re-render only when it changes.
      const beat = activeBeatForScroll(progress, beats.length);
      if (beat !== lastBeat) {
        lastBeat = beat;
        setActiveBeat(beat);
      }
    };

    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [beats, greedy, reduced]);

  return (
    <>
      <ShaderBackground state={field} />

      <div ref={containerRef} className="relative">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 lg:grid-cols-2 lg:gap-16">
          {/* Pinned track. */}
          <div className="lg:sticky lg:top-0 lg:h-screen lg:self-start">
            <div className="flex h-[52vh] flex-col justify-center lg:h-screen">
              <svg
                viewBox={`0 0 ${projection.width} ${projection.height}`}
                className="w-full"
                role="img"
                aria-label="Monza, drawn as you scroll through the lap"
              >
                <path
                  d={projection.path}
                  fill="none"
                  stroke={TOKENS.line}
                  strokeWidth={6}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.5}
                />
                <path
                  ref={pathRef}
                  d={projection.path}
                  fill="none"
                  stroke={TOKENS.deploy}
                  strokeWidth={5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <g ref={carRef}>
                  <circle r={11} fill="none" stroke={TOKENS.bone} strokeWidth={1} opacity={0.5} />
                  <circle r={5} fill={TOKENS.bone} />
                </g>
              </svg>
              <div
                ref={readoutRef}
                className="tabular mt-4 text-center text-xs tracking-[0.18em] text-[#6B7280]"
              >
                — km/h
              </div>
            </div>
          </div>

          {/* Narrative, scrolling past the pinned map. */}
          <div>
            {beats.map((beat, i) => (
              <section
                key={beat.id}
                aria-current={i === activeBeat ? "step" : undefined}
                className="flex min-h-screen flex-col justify-center py-16"
              >
                <div
                  className="transition-opacity duration-500 motion-reduce:transition-none"
                  style={{ opacity: reduced || i === activeBeat ? 1 : 0.32 }}
                >
                  <div className="text-[10px] uppercase tracking-[0.28em] text-[#FF2E17]">
                    {beat.kicker}
                  </div>
                  <h2 className="display mt-3 text-3xl leading-tight text-[#F2F0EB] sm:text-4xl">
                    {beat.title}
                  </h2>
                  <p className="mt-4 max-w-md text-sm leading-relaxed text-[#8A8F98]">
                    {beat.body}
                  </p>
                  {beat.readout && (
                    <div className="mt-6 inline-block border-l-2 border-[#FF2E17] pl-3">
                      <div className="text-[10px] uppercase tracking-[0.2em] text-[#6B7280]">
                        {beat.readout.label}
                      </div>
                      <div className="tabular text-xl text-[#F2F0EB]">
                        {beat.readout.value}
                      </div>
                    </div>
                  )}
                  {beat.id === "release" && (
                    <div className="mt-8">
                      <Link
                        href="/analysis"
                        className="focus-ring inline-flex items-center gap-2 rounded bg-[#FF2E17] px-5 py-3 text-xs uppercase tracking-[0.18em] text-[#08090A] transition-opacity hover:opacity-90"
                      >
                        Open the analysis
                        <span aria-hidden="true">→</span>
                      </Link>
                    </div>
                  )}
                </div>
              </section>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
