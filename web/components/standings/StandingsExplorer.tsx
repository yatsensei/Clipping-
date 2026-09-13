"use client";

import { useMemo, useState } from "react";
import type { StandingsData } from "@/lib/f1/queries";
import { gapToLeader, positionDeltas, progression } from "@/lib/f1/standings";
import type { StandingsSnapshot } from "@/lib/f1/types";
import { ProgressionChart } from "./ProgressionChart";
import { RoundScrubber } from "./RoundScrubber";
import { StandingsTable } from "./StandingsTable";

/**
 * The standings as a thing to explore rather than a table to read: every completed
 * round's table is in the props, and the reader scrubs through them. Deltas and gaps
 * are computed here, per round, because they depend on where the scrubber is.
 */
const EMPTY: StandingsSnapshot = { round: 0, raceName: null, rows: [] };

export function StandingsExplorer({ data }: { data: StandingsData }) {
  const { kind, snapshots, entities } = data;
  const [index, setIndex] = useState(snapshots.length - 1);

  const prog = useMemo(() => progression(snapshots), [snapshots]);
  // Hooks run before the empty-season guard below, so tolerate no snapshots here.
  const current = snapshots[index] ?? EMPTY;
  const previous = index > 0 ? snapshots[index - 1] : null;
  const deltas = useMemo(
    () => positionDeltas(current.rows, previous?.rows ?? null),
    [current.rows, previous?.rows],
  );
  const gaps = useMemo(() => gapToLeader(current.rows), [current.rows]);

  // Colour the top of the CURRENT table — the story at the scrubbed round, not the end.
  const highlight = current.rows
    .slice(0, kind === "drivers" ? 8 : 11)
    .map((r) => r.id);

  if (snapshots.length === 0) {
    return (
      <p className="rounded-lg border border-line bg-panel p-6 text-sm text-muted">
        No rounds have been classified yet this season.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <RoundScrubber snapshots={snapshots} index={index} onChange={setIndex} />
      <ProgressionChart
        progression={prog}
        entities={entities}
        highlight={highlight}
        cursor={index}
        onCursor={setIndex}
      />
      <StandingsTable
        kind={kind}
        rows={current.rows}
        entities={entities}
        deltas={deltas}
        gaps={gaps}
      />
    </div>
  );
}
