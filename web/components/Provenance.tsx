"use client";

import type { Provenance as ProvenanceData } from "@/lib/api";

/**
 * Says where the numbers came from and what is measured versus modelled.
 *
 * Not a footnote. Public F1 telemetry contains no energy channels at all, so every
 * deployment, state-of-charge and clipping figure on screen is model output. Presenting
 * them without saying so would be the interface claiming to know something it cannot.
 */
export function Provenance({ provenance }: { provenance: ProvenanceData }) {
  return (
    <div className="rounded-lg border border-[#262A30] bg-[#141619] p-3 text-[11px] leading-relaxed">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-[#3FE0D0]" />
        <span className="text-[10px] uppercase tracking-[0.18em] text-[#6B7280]">
          Provenance
        </span>
      </div>
      <p className="text-[#F2F0EB]">
        {provenance.session} · {provenance.reference_driver} ({provenance.reference_team}){" "}
        <span className="tabular text-[#6B7280]">
          {provenance.reference_lap_time_s.toFixed(3)}s
        </span>
      </p>
      <p className="mt-1 text-[#6B7280]">
        Geometry pooled from {provenance.laps_pooled} clean laps (
        {provenance.gps_samples.toLocaleString()} GPS samples).
      </p>
      <p className="mt-2 text-[#8A8F98]">{provenance.note}</p>
      {provenance.fallback_note && (
        <p className="mt-2 rounded border border-[#262A30] bg-[#08090A] p-2 text-[#8A8F98]">
          <span className="text-[#F2F0EB]">Fallback geometry. </span>
          {provenance.fallback_note}
        </p>
      )}
    </div>
  );
}

export function Legend() {
  const items = [
    { colour: "#FF2E17", label: "Deploying", width: 7, note: "thicker = more power" },
    { colour: "#3FE0D0", label: "Harvesting", width: 4 },
    { colour: "#8A8F98", label: "Clipping", width: 5.5, note: "asked for power, none left" },
    { colour: "#262A30", label: "Coasting / braking", width: 2.5 },
  ];
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2">
      {items.map((i) => (
        <div key={i.label} className="flex items-center gap-2">
          <svg width="26" height="10" aria-hidden="true">
            <line
              x1="1"
              y1="5"
              x2="25"
              y2="5"
              stroke={i.colour}
              strokeWidth={i.width}
              strokeLinecap="round"
            />
          </svg>
          <span className="text-[11px] text-[#F2F0EB]">
            {i.label}
            {i.note && <span className="text-[#6B7280]"> — {i.note}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
