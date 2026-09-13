import Link from "next/link";
import { Avatar } from "@/components/Avatar";
import { driverLabel } from "@/lib/f1/standings";
import type { Race } from "@/lib/f1/types";
import { teamStyle, teamVars } from "@/lib/teams";
import { Countdown } from "./Countdown";

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

export function LastRaceCard({ race }: { race: Race | null }) {
  if (!race || !race.Results?.length) {
    return (
      <Card kicker="Last race" title="No race classified yet">
        <p className="font-sans text-sm text-muted">The season has not started.</p>
      </Card>
    );
  }
  const podium = race.Results.slice(0, 3);
  const fastest = race.Results.find((r) => r.FastestLap?.rank === "1");
  const winnerGrid = Number(podium[0].grid);

  return (
    <Card
      kicker={`Last race · round ${race.round}`}
      title={race.raceName}
      subtitle={`${race.Circuit.circuitName} · ${dateFormat.format(new Date(race.date))}`}
    >
      <ol className="space-y-1.5">
        {podium.map((r, i) => {
          const teamId = r.Constructor.constructorId;
          return (
            <li key={r.Driver.driverId} style={teamVars(teamId)}>
              <Link
                href={`/drivers/${r.Driver.driverId}`}
                className="focus-ring flex items-center gap-3 rounded px-1 py-1 hover:bg-panel-high"
              >
                <span className="tabular w-4 text-xs text-muted">{i + 1}</span>
                <span className="team-bar h-7 w-1 rounded-full" aria-hidden="true" />
                <Avatar
                  kind="drivers"
                  id={r.Driver.driverId}
                  label={driverLabel(r.Driver)}
                  teamId={teamId}
                  size={28}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-sans text-sm text-ink">
                    {driverLabel(r.Driver)}
                  </span>
                  <span className="team-text block text-[9px] uppercase tracking-[0.14em]">
                    {teamStyle(teamId).short}
                  </span>
                </span>
                <span className="tabular text-xs text-muted">
                  {i === 0 ? r.Time?.time ?? r.status : r.Time?.time ?? r.status}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-3 text-[11px] text-muted">
        {winnerGrid > 1 && (
          <span>
            Won from <span className="tabular text-ink">P{winnerGrid}</span> on the grid
          </span>
        )}
        {fastest && (
          <span>
            Fastest lap{" "}
            <span className="tabular text-ink">{fastest.FastestLap?.Time.time}</span>{" "}
            {fastest.Driver.code ?? fastest.Driver.familyName}
          </span>
        )}
      </div>
    </Card>
  );
}

export function NextRaceCard({ race }: { race: Race | null }) {
  if (!race) {
    return (
      <Card kicker="Next race" title="Season complete">
        <p className="font-sans text-sm text-muted">See you next year.</p>
      </Card>
    );
  }
  const start = `${race.date}T${race.time ?? "00:00:00Z"}`;
  const sessions = [
    race.Sprint && { label: "Sprint", at: race.Sprint },
    race.Qualifying && { label: "Qualifying", at: race.Qualifying },
    { label: "Race", at: { date: race.date, time: race.time } },
  ].filter((s): s is { label: string; at: { date: string; time?: string } } => Boolean(s));

  return (
    <Card
      kicker={`Next race · round ${race.round}`}
      title={race.raceName}
      subtitle={`${race.Circuit.circuitName} · ${race.Circuit.Location.locality}, ${race.Circuit.Location.country}`}
    >
      <Countdown to={start} />
      <ul className="mt-3 space-y-1 border-t border-line pt-3 text-[11px]">
        {sessions.map((s) => (
          <li key={s.label} className="flex justify-between">
            <span className="uppercase tracking-[0.14em] text-muted">{s.label}</span>
            <span className="tabular text-ink">
              {dateFormat.format(new Date(s.at.date))}
              {s.at.time && <span className="ml-2 text-muted">{s.at.time.slice(0, 5)} UTC</span>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Card({
  kicker,
  title,
  subtitle,
  children,
}: {
  kicker: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted">{kicker}</div>
      <h2 className="display mt-1 text-lg text-ink">{title}</h2>
      {subtitle && <p className="mt-0.5 text-[11px] text-muted">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}
