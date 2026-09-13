import Link from "next/link";
import { Avatar } from "@/components/Avatar";
import type { Entity, StandingsRow } from "@/lib/f1/types";
import { teamStyle, teamVars } from "@/lib/teams";

/** A card in the drivers or teams grid: portrait, name, team, and the season so far. */
export function EntityCard({
  entity,
  standing,
  href,
  subtitle,
}: {
  entity: Entity;
  standing: StandingsRow | null;
  href: string;
  subtitle?: string;
}) {
  const team = teamStyle(entity.teamId);
  const isDriver = entity.kind === "drivers";
  return (
    <Link
      href={href}
      style={teamVars(entity.teamId)}
      className="focus-ring group relative flex items-center gap-4 overflow-hidden rounded-lg border border-line bg-panel p-4 transition-colors hover:border-(--team)"
    >
      <span
        className="team-bar absolute inset-y-0 left-0 w-1 transition-[width] group-hover:w-1.5"
        aria-hidden="true"
      />
      <Avatar
        kind={isDriver ? "drivers" : "teams"}
        id={entity.id}
        label={entity.label}
        teamId={entity.teamId}
        size={56}
        className="ml-1"
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-sans text-base text-ink">{entity.label}</span>
        <span className="team-text block truncate text-[10px] uppercase tracking-[0.16em]">
          {subtitle ?? (isDriver ? team.name || entity.teamId : entity.nationality)}
        </span>
      </span>
      <span className="text-right">
        <span className="tabular block text-lg text-ink">
          {standing ? `P${standing.position}` : "—"}
        </span>
        <span className="tabular block text-[10px] text-muted">
          {standing ? `${standing.points} pts` : "no points"}
        </span>
      </span>
    </Link>
  );
}
