import { cache } from "react";
import { TEAM_SHORT_NAMES } from "@/lib/teams";
import {
  getConstructorStandingsByRound,
  getCurrentConstructorStandings,
  getCurrentDriverStandings,
  getDriverStandingsByRound,
  getSchedule,
} from "./jolpica";
import { constructorEntities, driverEntities, toSnapshot } from "./standings";
import type { Entity, StandingsKind, StandingsSnapshot } from "./types";

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
