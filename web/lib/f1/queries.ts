import { cache } from "react";
import { TEAM_SHORT_NAMES } from "@/lib/teams";
import {
  getConstructorStandingsByRound,
  getCurrentConstructorStandings,
  getCurrentDriverStandings,
  getDriverStandingsByRound,
  getSchedule,
  getSeasonQualifying,
  getSeasonResults,
  getSeasonSprints,
} from "./jolpica";
import {
  constructorEntities,
  currentTeam,
  driverEntities,
  driverSeasonRows,
  headToHead,
  progression,
  teammateOf,
  toSnapshot,
} from "./standings";
import type {
  DriverRoundRow,
  Entity,
  HeadToHead,
  Progression,
  StandingsKind,
  StandingsRow,
  StandingsSnapshot,
} from "./types";

/**
 * Page-level queries: the fetchers in ./jolpica composed with the pure transforms in
 * ./standings. Server-only, and React.cache-wrapped so a layout, its page and
 * generateMetadata share one pass.
 */

export interface StandingsData {
  kind: StandingsKind;
  /** The most recent round the live table includes. */
  latest: number;
  /** One snapshot per round that has a table, in order. */
  snapshots: StandingsSnapshot[];
  entities: Record<string, Entity>;
}

export const loadStandings = cache(async (kind: StandingsKind): Promise<StandingsData> => {
  const schedule = await getSchedule();
  const names = new Map(schedule.map((r) => [Number(r.round), r.raceName]));

  if (kind === "drivers") {
    const [{ latest, rounds }, current] = await Promise.all([
      getDriverStandingsByRound(),
      getCurrentDriverStandings(),
    ]);
    // Entities from every round, later rounds overriding, so a driver who left the
    // grid mid-season still resolves on the rounds they raced.
    const entities: Record<string, Entity> = {};
    for (const rows of [...rounds, current.rows]) Object.assign(entities, driverEntities(rows));
    return {
      kind,
      latest,
      snapshots: rounds
        .map((rows, i) => toSnapshot(kind, i + 1, names.get(i + 1) ?? null, rows))
        .filter((s) => s.rows.length > 0),
      entities,
    };
  }

  const [{ latest, rounds }, current] = await Promise.all([
    getConstructorStandingsByRound(),
    getCurrentConstructorStandings(),
  ]);
  const entities: Record<string, Entity> = {};
  for (const rows of [...rounds, current.rows]) {
    Object.assign(entities, constructorEntities(rows, TEAM_SHORT_NAMES));
  }
  return {
    kind,
    latest,
    snapshots: rounds
      .map((rows, i) => toSnapshot(kind, i + 1, names.get(i + 1) ?? null, rows))
      .filter((s) => s.rows.length > 0),
    entities,
  };
});

// ------------------------------------------------------------------ profiles

export interface DriverProfile {
  entity: Entity;
  /** Current championship row; null if the driver has not scored a classification. */
  standing: StandingsRow | null;
  teammate: { entity: Entity; standing: StandingsRow | null } | null;
  headToHead: HeadToHead | null;
  rows: DriverRoundRow[];
  progression: Progression;
}

/** Everything a driver page shows, or null for an id not in this season's standings. */
export const loadDriverProfile = cache(async (driverId: string): Promise<DriverProfile | null> => {
  const standings = await loadStandings("drivers");
  const entity = standings.entities[driverId];
  if (!entity) return null;

  const [schedule, results, qualifying, sprints, current] = await Promise.all([
    getSchedule(),
    getSeasonResults(),
    getSeasonQualifying(),
    getSeasonSprints(),
    getCurrentDriverStandings(),
  ]);

  const latest = standings.snapshots[standings.snapshots.length - 1];
  const standingOf = (id: string) => latest?.rows.find((r) => r.id === id) ?? null;
  const mateId = teammateOf(driverId, current.rows);
  const mate = mateId ? standings.entities[mateId] : null;

  return {
    entity,
    standing: standingOf(driverId),
    teammate: mate ? { entity: mate, standing: standingOf(mate.id) } : null,
    headToHead: mateId ? headToHead(driverId, mateId, results, qualifying) : null,
    rows: driverSeasonRows(driverId, schedule, results, qualifying, sprints),
    progression: progression(standings.snapshots),
  };
});

export interface TeamProfile {
  entity: Entity;
  standing: StandingsRow | null;
  drivers: { entity: Entity; standing: StandingsRow | null; rows: DriverRoundRow[] }[];
  headToHead: HeadToHead | null;
  progression: Progression;
  /** All constructors, for the progression chart's context lines. */
  teamEntities: Record<string, Entity>;
}

export const loadTeamProfile = cache(async (constructorId: string): Promise<TeamProfile | null> => {
  const [teams, drivers] = await Promise.all([
    loadStandings("constructors"),
    loadStandings("drivers"),
  ]);
  const entity = teams.entities[constructorId];
  if (!entity) return null;

  const [schedule, results, qualifying, sprints, current] = await Promise.all([
    getSchedule(),
    getSeasonResults(),
    getSeasonQualifying(),
    getSeasonSprints(),
    getCurrentDriverStandings(),
  ]);

  const latestTeams = teams.snapshots[teams.snapshots.length - 1];
  const latestDrivers = drivers.snapshots[drivers.snapshots.length - 1];
  const lineup = current.rows
    .filter((r) => currentTeam(r) === constructorId)
    .sort((a, b) => Number(b.points) - Number(a.points))
    .map((r) => r.Driver.driverId);

  return {
    entity,
    standing: latestTeams?.rows.find((r) => r.id === constructorId) ?? null,
    drivers: lineup.map((id) => ({
      entity: drivers.entities[id],
      standing: latestDrivers?.rows.find((r) => r.id === id) ?? null,
      rows: driverSeasonRows(id, schedule, results, qualifying, sprints),
    })),
    headToHead:
      lineup.length >= 2 ? headToHead(lineup[0], lineup[1], results, qualifying) : null,
    progression: progression(teams.snapshots),
    teamEntities: teams.entities,
  };
});
