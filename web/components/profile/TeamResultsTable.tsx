import type { DriverRoundRow, Entity } from "@/lib/f1/types";

/** Both cars, weekend by weekend: each driver's finish and the team's points haul. */
export function TeamResultsTable({
  drivers,
}: {
  drivers: { entity: Entity; rows: DriverRoundRow[] }[];
}) {
  const rounds = drivers[0]?.rows ?? [];
  // Column count depends on the line-up, so the template is inline rather than a
  // Tailwind class the scanner could not see.
  const cols = { gridTemplateColumns: `2rem minmax(0,1fr) repeat(${drivers.length}, 4.5rem) 3.5rem` };

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-panel">
      <div role="table" aria-label="Season results by car" className="min-w-[480px]">
        <div
          role="row"
          style={cols}
          className="grid items-center gap-x-3 border-b border-line px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-muted"
        >
          <span role="columnheader">Rd</span>
          <span role="columnheader">Grand Prix</span>
          {drivers.map((d) => (
            <span key={d.entity.id} role="columnheader" className="text-right">
              {d.entity.short}
            </span>
          ))}
          <span role="columnheader" className="text-right">Pts</span>
        </div>
        {rounds.map((r, i) => {
          const weekend = drivers.map((d) => d.rows[i]);
          const ran = weekend.some((w) => w?.raced || w?.sprint);
          const points = weekend.reduce((s, w) => s + (w?.points ?? 0), 0);
          return (
            <div
              key={r.round}
              role="row"
              style={cols}
              className={`grid items-center gap-x-3 border-b border-line px-3 py-1.5 text-xs last:border-b-0 ${
                ran ? "" : "text-muted"
              }`}
            >
              <span role="cell" className="tabular text-muted">
                {r.round}
              </span>
              <span role="cell" className="truncate font-sans text-ink">
                {r.raceName.replace(/ Grand Prix$/, "")}
              </span>
              {weekend.map((w, k) => (
                <span key={k} role="cell" className="tabular text-right">
                  {!w?.raced ? (
                    "·"
                  ) : w.finish == null ? (
                    <span className="text-clip" title={w.status ?? undefined}>
                      {w.positionText}
                    </span>
                  ) : (
                    <span className={w.finish === 1 ? "text-warn" : w.finish <= 10 ? "text-ink" : "text-muted"}>
                      {w.finish}
                    </span>
                  )}
                </span>
              ))}
              <span role="cell" className="tabular text-right text-ink">
                {ran ? points : "·"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
