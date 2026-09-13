import Link from "next/link";
import { Avatar } from "@/components/Avatar";
import type { StandingsData } from "@/lib/f1/queries";
import { teamStyle, teamVars } from "@/lib/teams";

/**
 * The top of the site: what it is, and the state of both championships right now.
 * The leaders are the live hook; the sentence is the promise.
 */
export function Hero({
  drivers,
  constructors,
  progress,
}: {
  drivers: StandingsData;
  constructors: StandingsData;
  progress: { done: number; total: number };
}) {
  const dRows = drivers.snapshots[drivers.snapshots.length - 1]?.rows.slice(0, 3) ?? [];
  const cRows = constructors.snapshots[constructors.snapshots.length - 1]?.rows.slice(0, 3) ?? [];

  return (
    <section className="grid gap-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:items-end">
      <div>
        <div className="text-[10px] uppercase tracking-[0.28em] text-deploy">
          Formula 1 · 2026 · round {progress.done} of {progress.total}
        </div>
        <h1 className="display mt-3 text-4xl leading-[1.05] text-ink sm:text-5xl lg:text-6xl">
          The season, and the
          <br />
          physics underneath it.
        </h1>
        <p className="mt-5 max-w-lg font-sans text-base leading-relaxed text-muted">
          Live championship standings and profiles for every driver and team — and an
          optimiser that works out, metre by metre, where a 2026 car should spend its
          battery around a lap.
        </p>
        <div className="mt-7 flex flex-wrap gap-3 text-[11px] uppercase tracking-[0.18em]">
          <Link
            href="/standings/drivers"
            className="focus-ring rounded bg-deploy px-5 py-3 text-surface transition-opacity hover:opacity-90"
          >
            Standings →
          </Link>
          <Link
            href="/energy"
            className="focus-ring rounded border border-line px-5 py-3 text-ink transition-colors hover:border-deploy"
          >
            The energy problem
          </Link>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Leaders
          title="Drivers"
          href="/standings/drivers"
          rows={dRows.map((r) => ({
            id: r.id,
            kind: "drivers" as const,
            label: drivers.entities[r.id]?.label ?? r.id,
            sub: teamStyle(r.teamId).short,
            teamId: r.teamId,
            points: r.points,
            href: `/drivers/${r.id}`,
          }))}
        />
        <Leaders
          title="Constructors"
          href="/standings/constructors"
          rows={cRows.map((r) => ({
            id: r.id,
            kind: "teams" as const,
            label: constructors.entities[r.id]?.label ?? r.id,
            sub: constructors.entities[r.id]?.nationality ?? "",
            teamId: r.teamId,
            points: r.points,
            href: `/teams/${r.id}`,
          }))}
        />
      </div>
    </section>
  );
}

function Leaders({
  title,
  href,
  rows,
}: {
  title: string;
  href: string;
  rows: {
    id: string;
    kind: "drivers" | "teams";
    label: string;
    sub: string;
    teamId: string;
    points: number;
    href: string;
  }[];
}) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted">{title}</span>
        <Link href={href} className="focus-ring text-[10px] uppercase tracking-[0.14em] text-muted hover:text-ink">
          Full table →
        </Link>
      </div>
      <ol className="space-y-1">
        {rows.map((r, i) => (
          <li key={r.id} style={teamVars(r.teamId)}>
            <Link
              href={r.href}
              className="focus-ring flex items-center gap-3 rounded px-1 py-1 transition-colors hover:bg-panel-high"
            >
              <span className="tabular w-4 text-xs text-muted">{i + 1}</span>
              <span className="team-bar h-7 w-1 rounded-full" aria-hidden="true" />
              <Avatar kind={r.kind} id={r.id} label={r.label} teamId={r.teamId} size={28} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-sans text-sm text-ink">{r.label}</span>
                <span className="team-text block truncate text-[9px] uppercase tracking-[0.14em]">
                  {r.sub}
                </span>
              </span>
              <span className="tabular text-sm text-ink">{r.points}</span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
