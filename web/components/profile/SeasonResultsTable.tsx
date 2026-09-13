import type { DriverRoundRow } from "@/lib/f1/types";

/**
 * One row per scheduled round. Rounds that have not run yet are shown, greyed, so the
 * table reads as a calendar with results filling in rather than a list that grows.
 */
export function SeasonResultsTable({
  rows,
  hasSprints,
}: {
  rows: DriverRoundRow[];
  hasSprints: boolean;
}) {
  const grid = hasSprints
    ? "grid-cols-[2rem_minmax(0,1fr)_3rem_3rem_3.5rem_3rem_3.5rem]"
    : "grid-cols-[2rem_minmax(0,1fr)_3rem_3rem_3rem_3.5rem]";
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-panel">
      <div role="table" aria-label="Season results" className="min-w-[520px]">
        <div
          role="row"
          className={`grid ${grid} items-center gap-x-3 border-b border-line px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-muted`}
        >
          <span role="columnheader">Rd</span>
          <span role="columnheader">Grand Prix</span>
          <span role="columnheader" className="text-right">Quali</span>
          <span role="columnheader" className="text-right">Grid</span>
          {hasSprints && (
            <span role="columnheader" className="text-right">Sprint</span>
          )}
          <span role="columnheader" className="text-right">Race</span>
          <span role="columnheader" className="text-right">Pts</span>
        </div>
        {rows.map((r) => (
          <div
            key={r.round}
            role="row"
            className={`grid ${grid} items-center gap-x-3 border-b border-line px-3 py-1.5 text-xs last:border-b-0 ${
              r.raced || r.sprint ? "" : "text-muted"
            }`}
          >
            <span role="cell" className="tabular text-muted">
              {r.round}
            </span>
            <span role="cell" className="truncate font-sans text-ink">
              {r.raceName.replace(/ Grand Prix$/, "")}
              <span className="ml-2 text-[10px] uppercase tracking-[0.12em] text-muted">
                {r.country}
              </span>
            </span>
            <span role="cell" className="tabular text-right text-muted">
              {r.qualiPosition ?? "·"}
            </span>
            <span role="cell" className="tabular text-right text-muted">
              {r.grid == null ? "·" : r.grid === 0 ? "pit" : r.grid}
            </span>
            {hasSprints && (
              <span role="cell" className="tabular text-right">
                {r.sprint ? <Finish finish={r.sprint.finish} text={r.sprint.positionText} /> : "·"}
              </span>
            )}
            <span role="cell" className="tabular text-right">
              {r.raced ? (
                <Finish finish={r.finish} text={r.positionText ?? ""} status={r.status} />
              ) : (
                "·"
              )}
              {r.fastestLap && (
                <span className="ml-1 text-[9px] text-deploy" title="Fastest lap">
                  FL
                </span>
              )}
            </span>
            <span role="cell" className="tabular text-right text-ink">
              {r.raced || r.sprint ? r.points : "·"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Finish({
  finish,
  text,
  status,
}: {
  finish: number | null;
  text: string;
  status?: string | null;
}) {
  if (finish == null) {
    return (
      <span className="text-clip" title={status ?? undefined}>
        {text || "DNF"}
      </span>
    );
  }
  const tone =
    finish === 1
      ? "text-warn"
      : finish <= 3
        ? "text-ink"
        : finish <= 10
          ? "text-ink"
          : "text-muted";
  return <span className={tone}>{finish}</span>;
}
