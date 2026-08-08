"use client";

import type { Comparison, Strategy } from "@/lib/api";
import { formatLap } from "@/lib/track";

/**
 * The headline figures.
 *
 * The gain is never rendered without naming what it is measured against — a gain with no
 * stated baseline is meaningless, and the API sends the statement precisely so it cannot
 * be dropped here. Greedy's lap time is always accompanied by its energy debt, because on
 * every circuit it is the fastest single lap and the slowest thing to actually run twice.
 */
export function Headline({
  comparison,
  strategy,
}: {
  comparison: Comparison;
  strategy: Strategy;
}) {
  const clipPct =
    (100 * strategy.clipping.filter(Boolean).length) / strategy.clipping.length;
  const harvested = comparison.strategies.find((s) => s.mode === "optimal")
    ?.energy_harvested_mj;

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-[#262A30] bg-[#141619] p-4">
        <div className="text-[10px] uppercase tracking-[0.2em] text-[#6B7280]">
          Lap time gained
        </div>
        <div className="display mt-1 text-4xl text-[#FF2E17] tabular leading-none">
          {comparison.gain_vs_uniform_s.toFixed(3)}
          <span className="text-xl text-[#6B7280] ml-1">s</span>
        </div>
        <p className="mt-2 text-[11px] leading-snug text-[#6B7280]">
          versus <span className="text-[#F2F0EB]">uniform constant deployment</span>.{" "}
          {comparison.baseline_statement}
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-2">
        <Stat label="Optimal lap" value={formatLap(strategy.lap_time_s)} unit="s" />
        <Stat
          label="Energy deployed"
          value={strategy.energy_deployed_mj.toFixed(2)}
          unit="MJ"
        />
        <Stat
          label="Energy harvested"
          value={harvested != null ? harvested.toFixed(2) : "—"}
          unit="MJ"
        />
        <Stat
          label="Lap clipping"
          value={clipPct.toFixed(1)}
          unit="%"
          tone={clipPct > 5 ? "clip" : "normal"}
        />
      </dl>

      <div className="rounded-lg border border-[#262A30] bg-[#141619] p-3">
        <div className="text-[10px] uppercase tracking-[0.2em] text-[#6B7280] mb-2">
          All strategies
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[#6B7280] text-[10px] uppercase tracking-wider">
              <th className="text-left font-normal pb-1">Mode</th>
              <th className="text-right font-normal pb-1">Lap</th>
              <th className="text-right font-normal pb-1">Clip</th>
              <th className="text-right font-normal pb-1">Repeatable</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {comparison.strategies.map((s) => (
              <tr key={s.mode} className="border-t border-[#262A30]">
                <td className="py-1.5 capitalize text-[#F2F0EB]">{s.mode}</td>
                <td className="py-1.5 text-right">{s.lap_time_s.toFixed(3)}</td>
                <td className="py-1.5 text-right text-[#6B7280]">
                  {s.clipping_pct.toFixed(0)}%
                </td>
                <td className="py-1.5 text-right">
                  {s.repeatable ? (
                    <span className="text-[#3FE0D0]">yes</span>
                  ) : (
                    <span className="text-[#8A8F98]">
                      no · −{comparison.greedy_energy_debt_mj.toFixed(2)} MJ
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] leading-snug text-[#6B7280]">
          {comparison.greedy_caveat}
        </p>
      </div>

      {comparison.learned_policy && (
        <div className="rounded-lg border border-[#262A30] bg-[#141619] p-3">
          <div className="text-[10px] uppercase tracking-[0.2em] text-[#6B7280]">
            Learned policy (held out)
          </div>
          <div className="tabular mt-1 text-lg text-[#F2F0EB]">
            {comparison.learned_policy.gain_retained_pct.toFixed(0)}%
            <span className="text-xs text-[#6B7280] ml-2">of the gain retained</span>
          </div>
          {!comparison.learned_policy.comparable && (
            <p className="mt-1 text-[11px] leading-snug text-[#8A8F98]">
              Not comparable: this lap ended with less energy than it started, so its
              time flatters the model. The optimiser is periodic by construction; the
              cloned policy has no mechanism that enforces it.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  tone = "normal",
}: {
  label: string;
  value: string;
  unit: string;
  tone?: "normal" | "clip";
}) {
  return (
    <div className="rounded-lg border border-[#262A30] bg-[#141619] p-3">
      <dt className="text-[10px] uppercase tracking-[0.16em] text-[#6B7280]">
        {label}
      </dt>
      <dd
        className={`tabular mt-1 text-xl ${
          tone === "clip" ? "text-[#8A8F98]" : "text-[#F2F0EB]"
        }`}
      >
        {value}
        <span className="text-xs text-[#6B7280] ml-1">{unit}</span>
      </dd>
    </div>
  );
}
