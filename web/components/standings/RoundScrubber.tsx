"use client";

import type { StandingsSnapshot } from "@/lib/f1/types";

/**
 * Step through the season. The range input is the primary control; the buttons and
 * arrow keys are for people who want one round at a time. The race name is announced
 * politely so a screen reader hears where the table now stands.
 */
export function RoundScrubber({
  snapshots,
  index,
  onChange,
}: {
  snapshots: StandingsSnapshot[];
  index: number;
  onChange: (index: number) => void;
}) {
  const last = snapshots.length - 1;
  const current = snapshots[index];
  const isLatest = index === last;

  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onChange(Math.max(0, index - 1))}
            disabled={index === 0}
            aria-label="Previous round"
            className="focus-ring rounded border border-line px-2.5 py-1.5 text-xs text-muted transition-colors hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
          >
            ←
          </button>
          <button
            type="button"
            onClick={() => onChange(Math.min(last, index + 1))}
            disabled={isLatest}
            aria-label="Next round"
            className="focus-ring rounded border border-line px-2.5 py-1.5 text-xs text-muted transition-colors hover:text-ink disabled:opacity-40 disabled:hover:text-muted"
          >
            →
          </button>
        </div>

        <label className="flex min-w-[200px] flex-1 items-center gap-3">
          <span className="sr-only">Round</span>
          <input
            type="range"
            min={0}
            max={last}
            step={1}
            value={index}
            onChange={(e) => onChange(Number(e.target.value))}
            className="focus-ring w-full accent-deploy"
            aria-valuetext={`Round ${current.round}: ${current.raceName ?? ""}`}
          />
        </label>

        <div className="min-w-[220px] text-right" aria-live="polite">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted">
            After round{" "}
            <span className="tabular text-ink">{current.round}</span> of{" "}
            <span className="tabular">{snapshots[last].round}</span>
            {isLatest && <span className="ml-2 text-harvest">latest</span>}
          </div>
          <div className="mt-0.5 truncate font-sans text-sm text-ink">
            {current.raceName ?? `Round ${current.round}`}
          </div>
        </div>
      </div>
    </div>
  );
}
