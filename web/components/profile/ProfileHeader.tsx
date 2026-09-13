import Link from "next/link";
import { Avatar } from "@/components/Avatar";
import type { Entity, StandingsRow } from "@/lib/f1/types";
import { teamStyle, teamVars } from "@/lib/teams";

/**
 * The band at the top of a profile: a wash of the team colour, the portrait or logo,
 * and the three numbers that matter this season. Body text stays in --ink; the team
 * colour is a wash, a bar and the small-caps line, never the prose.
 */
export function ProfileHeader({
  entity,
  standing,
  facts,
  teamLink = true,
}: {
  entity: Entity;
  standing: StandingsRow | null;
  /** Small label/value pairs under the name: nationality, age, number... */
  facts: { label: string; value: string }[];
  teamLink?: boolean;
}) {
  const team = teamStyle(entity.teamId);
  const isDriver = entity.kind === "drivers";

  return (
    <header
      className="team-wash relative overflow-hidden rounded-lg border border-line"
      style={teamVars(entity.teamId)}
    >
      <span className="team-bar absolute inset-y-0 left-0 w-1.5" aria-hidden="true" />
      <div className="flex flex-col gap-5 p-5 pl-7 sm:flex-row sm:items-center sm:gap-7 sm:p-6 sm:pl-8">
        <Avatar
          kind={isDriver ? "drivers" : "teams"}
          id={entity.id}
          label={entity.label}
          teamId={entity.teamId}
          size={96}
        />

        <div className="min-w-0 flex-1">
          <div className="team-text text-[10px] uppercase tracking-[0.28em]">
            {isDriver ? (
              teamLink ? (
                <Link href={`/teams/${entity.teamId}`} className="focus-ring hover:underline">
                  {team.name || entity.teamId}
                </Link>
              ) : (
                team.name
              )
            ) : (
              entity.nationality
            )}
          </div>
          <h1 className="display mt-1 text-3xl leading-tight text-ink sm:text-4xl">
            {entity.label}
          </h1>
          <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px]">
            {facts.map((f) => (
              <div key={f.label} className="flex items-baseline gap-1.5">
                <dt className="uppercase tracking-[0.16em] text-muted">{f.label}</dt>
                <dd className="tabular text-ink">{f.value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <dl className="grid grid-cols-3 gap-2 sm:gap-3">
          <Stat label="Position" value={standing ? `P${standing.position}` : "—"} />
          <Stat label="Points" value={standing ? String(standing.points) : "—"} />
          <Stat label="Wins" value={standing ? String(standing.wins) : "—"} />
        </dl>
      </div>
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-center sm:min-w-[84px]">
      <dt className="text-[9px] uppercase tracking-[0.18em] text-muted">{label}</dt>
      <dd className="tabular mt-0.5 text-xl text-ink">{value}</dd>
    </div>
  );
}
