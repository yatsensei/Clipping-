"use client";

import { useEffect, useState } from "react";
import {
  MODE_DESCRIPTION,
  MODE_LABEL,
  api,
  type CircuitListItem,
  type Comparison,
  type Geometry,
  type Strategy,
  type StrategyMode,
} from "@/lib/api";
import { usePlayback } from "@/lib/usePlayback";
import { CircuitSelector } from "./CircuitSelector";
import { Headline } from "./Headline";
import { Nav } from "./Nav";
import { Legend, Provenance } from "./Provenance";
import { TrackMap } from "./TrackMap";
import { Traces } from "./Traces";
import { Transport } from "./Transport";

const MODES: StrategyMode[] = ["optimal", "uniform", "greedy"];

export function Analysis({ circuits }: { circuits: CircuitListItem[] }) {
  const solved = circuits.filter((c) => c.has_strategy);
  const [circuitId, setCircuitId] = useState(
    solved.find((c) => c.circuit_id === "monza")?.circuit_id ??
      solved[0]?.circuit_id ??
      "",
  );
  const [mode, setMode] = useState<StrategyMode>("optimal");
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Mark the pending request during render rather than at the top of the effect, which
  // would queue a second render pass on every circuit or mode change.
  const request = `${circuitId}|${mode}`;
  const [seenRequest, setSeenRequest] = useState(request);
  if (request !== seenRequest) {
    setSeenRequest(request);
    setLoading(true);
    setError(null);
  }

  useEffect(() => {
    if (!circuitId) return;
    let alive = true;
    Promise.all([
      api.geometry(circuitId),
      api.strategy(circuitId, mode),
      api.comparison(circuitId),
    ])
      .then(([g, s, c]) => {
        if (!alive) return;
        setGeometry(g);
        setStrategy(s);
        setComparison(c);
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [circuitId, mode]);

  const stepM = geometry?.step_m ?? 5;
  const playback = usePlayback(strategy, stepM);
  const capacity = comparison ? Math.max(4, comparison.harvest_cap_mj / 2) : 4;

  const circuit = circuits.find((c) => c.circuit_id === circuitId);

  return (
    <div className="min-h-screen bg-[#08090A]">
      <Nav />
      {circuit && (
        <header className="border-b border-[#262A30] px-4 py-2.5 sm:px-6">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h1 className="text-sm text-[#F2F0EB]">{circuit.event_name}</h1>
            <div className="tabular text-[11px] text-[#6B7280]">
              {(circuit.lap_distance_m / 1000).toFixed(3)} km ·{" "}
              {circuit.corner_count} corners · round {circuit.round_number} ·{" "}
              {circuit.provenance}
            </div>
          </div>
        </header>
      )}

      <div className="grid gap-4 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <main className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div
              className="flex rounded border border-[#262A30] overflow-hidden"
              role="group"
              aria-label="Deployment strategy"
            >
              {MODES.map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  aria-pressed={mode === m}
                  // Without an explicit label the title becomes the accessible name, so
                  // the button announces its description instead of "Optimal".
                  aria-label={MODE_LABEL[m]}
                  title={MODE_DESCRIPTION[m]}
                  className={`focus-ring px-3 py-1.5 text-xs uppercase tracking-[0.14em] transition-colors ${
                    mode === m
                      ? "bg-[#FF2E17] text-[#08090A]"
                      : "text-[#6B7280] hover:text-[#F2F0EB]"
                  }`}
                >
                  {MODE_LABEL[m]}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-[#6B7280]">{MODE_DESCRIPTION[mode]}</p>
          </div>

          {error && (
            <div className="rounded border border-[#FF2E17] bg-[#141619] p-4 text-sm">
              <p className="text-[#FF2E17]">Could not load this circuit.</p>
              <p className="mt-1 text-[11px] text-[#6B7280]">{error}</p>
              <p className="mt-2 text-[11px] text-[#6B7280]">
                Is the API running? <code>uv run uvicorn api.main:app</code>
              </p>
            </div>
          )}

          {geometry && strategy && (
            <>
              {/* Fixed height, not intrinsic. Sizing the map by width alone let a tall
                  circuit run past the bottom of the viewport, so only half the lap was
                  ever visible; the SVG now letterboxes inside a box that always fits. */}
              <div className="h-[46vh] min-h-[280px] rounded-lg border border-[#262A30] bg-[#141619] p-2 sm:h-[52vh] lg:h-[calc(100vh-15rem)] lg:max-h-[640px]">
                <TrackMap
                  geometry={geometry}
                  strategy={strategy}
                  carIndex={playback.index}
                  socCapacityMj={capacity}
                />
              </div>

              <Transport
                playing={playback.playing}
                speed={playback.speed}
                elapsed={playback.elapsed}
                total={playback.total}
                onToggle={playback.toggle}
                onRestart={playback.restart}
                onSpeed={playback.setSpeed}
                onScrub={playback.scrubTo}
              />

              <Legend />

              {!strategy.repeatable && strategy.repeatability_note && (
                <p className="rounded border border-[#8A8F98] bg-[#141619] p-3 text-[11px] text-[#8A8F98]">
                  {strategy.repeatability_note}
                </p>
              )}

              <div className="rounded-lg border border-[#262A30] bg-[#141619] p-3">
                <Traces
                  strategy={strategy}
                  carIndex={playback.index}
                  socCapacityMj={capacity}
                />
              </div>
            </>
          )}

          {loading && !geometry && (
            <div className="h-64 animate-pulse rounded-lg border border-[#262A30] bg-[#141619]" />
          )}
        </main>

        <aside className="space-y-4">
          {comparison && strategy && (
            <Headline comparison={comparison} strategy={strategy} />
          )}
          {geometry && <Provenance provenance={geometry.provenance} />}
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-[#6B7280]">
              Circuit
            </div>
            <CircuitSelector
              circuits={circuits}
              selected={circuitId}
              onSelect={setCircuitId}
            />
          </div>
        </aside>
      </div>
    </div>
  );
}
