import type {
  ConstructorStandingRow,
  DriverRoundRow,
  DriverStandingRow,
  Entity,
  HeadToHead,
  Progression,
  Race,
  StandingsKind,
  StandingsRow,
  StandingsSnapshot,
} from "./types";

/**
 * Pure transforms from Jolpica rows to what the UI renders. No I/O, no dates read from
 * the clock, so everything here is testable against captured fixtures.
 */

// ------------------------------------------------------------------- parsing

/** A classified position, or null for "R", "D", "W", "E" and friends. */
export function parsePos(text: string | undefined | null): number | null {
  if (text == null) return null;
  const n = Number(text);
  return Number.isInteger(n) && n > 0 ? n : null;
}

/** The team a driver currently races for: the LAST constructor listed this season. */
export function currentTeam(row: DriverStandingRow): string {
  return row.Constructors[row.Constructors.length - 1]?.constructorId ?? "";
}

export function driverLabel(d: { givenName: string; familyName: string }): string {
  return `${d.givenName} ${d.familyName}`;
}

// ----------------------------------------------------------------- snapshots

export function toSnapshot(
  kind: StandingsKind,
  round: number,
  raceName: string | null,
  rows: DriverStandingRow[] | ConstructorStandingRow[],
): StandingsSnapshot {
  const mapped: StandingsRow[] =
    kind === "drivers"
      ? (rows as DriverStandingRow[]).map((r) => ({
          id: r.Driver.driverId,
          teamId: currentTeam(r),
          position: Number(r.position),
          points: Number(r.points),
          wins: Number(r.wins),
        }))
      : (rows as ConstructorStandingRow[]).map((r) => ({
          id: r.Constructor.constructorId,
          teamId: r.Constructor.constructorId,
          position: Number(r.position),
          points: Number(r.points),
          wins: Number(r.wins),
        }));
  mapped.sort((a, b) => a.position - b.position);
  return { round, raceName, rows: mapped };
}

export function driverEntities(rows: DriverStandingRow[]): Record<string, Entity> {
  const out: Record<string, Entity> = {};
  for (const r of rows) {
    out[r.Driver.driverId] = {
      id: r.Driver.driverId,
      kind: "drivers",
      label: driverLabel(r.Driver),
      short: r.Driver.code ?? r.Driver.familyName.slice(0, 3).toUpperCase(),
      teamId: currentTeam(r),
      number: r.Driver.permanentNumber ?? null,
      nationality: r.Driver.nationality,
      url: r.Driver.url,
      givenName: r.Driver.givenName,
      familyName: r.Driver.familyName,
      dateOfBirth: r.Driver.dateOfBirth,
    };
  }
  return out;
}

export function constructorEntities(
  rows: ConstructorStandingRow[],
  /** Display names to prefer over the API's ("McLaren" rather than "McLaren F1 Team"). */
  names: Record<string, { name: string; short: string }> = {},
): Record<string, Entity> {
  const out: Record<string, Entity> = {};
  for (const r of rows) {
    const id = r.Constructor.constructorId;
    out[id] = {
      id,
      kind: "constructors",
      label: names[id]?.name ?? r.Constructor.name,
      short: names[id]?.short ?? r.Constructor.name,
      teamId: id,
      number: null,
      nationality: r.Constructor.nationality,
      url: r.Constructor.url,
    };
  }
  return out;
}

// ------------------------------------------------------------------- deltas

/**
 * Places gained since the previous round: positive = moved up. `null` for an entrant
 * with no previous position (round 1, or a mid-season substitute).
 */
export function positionDeltas(
  current: StandingsRow[],
  previous: StandingsRow[] | null,
): Record<string, number | null> {
  const before = new Map(previous?.map((r) => [r.id, r.position]) ?? []);
  const out: Record<string, number | null> = {};
  for (const r of current) {
    const was = before.get(r.id);
    out[r.id] = was == null ? null : was - r.position;
  }
  return out;
}

export function gapToLeader(rows: StandingsRow[]): Record<string, number> {
  const top = rows.reduce((m, r) => Math.max(m, r.points), 0);
  return Object.fromEntries(rows.map((r) => [r.id, top - r.points]));
}

// ----------------------------------------------------------------- progression

export function progression(snapshots: StandingsSnapshot[]): Progression {
  const ids = new Set<string>();
  for (const s of snapshots) for (const r of s.rows) ids.add(r.id);

  const points: Record<string, (number | null)[]> = {};
  const positions: Record<string, (number | null)[]> = {};
  for (const id of ids) {
    points[id] = snapshots.map((s) => s.rows.find((r) => r.id === id)?.points ?? null);
    positions[id] = snapshots.map(
      (s) => s.rows.find((r) => r.id === id)?.position ?? null,
    );
  }

  // Ordered by final standing so callers can slice the top N without re-sorting.
  const last = snapshots[snapshots.length - 1];
  const order = [...ids].sort((a, b) => {
    const pa = last?.rows.find((r) => r.id === a)?.position ?? Infinity;
    const pb = last?.rows.find((r) => r.id === b)?.position ?? Infinity;
    return pa - pb;
  });

  return {
    rounds: snapshots.map((s) => s.round),
    raceNames: snapshots.map((s) => s.raceName),
    ids: order,
    points,
    positions,
  };
}

// ------------------------------------------------------------------- results

/** One row per scheduled round, whether or not it has run. */
export function driverSeasonRows(
  driverId: string,
  schedule: Race[],
  results: Race[],
  qualifying: Race[],
  sprints: Race[],
): DriverRoundRow[] {
  const byRound = (races: Race[]) => new Map(races.map((r) => [Number(r.round), r]));
  const res = byRound(results);
  const qual = byRound(qualifying);
  const spr = byRound(sprints);

  return schedule.map((race) => {
    const round = Number(race.round);
    const result = res.get(round)?.Results?.find((r) => r.Driver.driverId === driverId);
    const q = qual.get(round)?.QualifyingResults?.find((r) => r.Driver.driverId === driverId);
    const s = spr.get(round)?.SprintResults?.find((r) => r.Driver.driverId === driverId);

    return {
      round,
      raceName: race.raceName,
      circuitId: race.Circuit.circuitId,
      country: race.Circuit.Location.country,
      date: race.date,
      raced: result != null,
      grid: result ? parsePos(result.grid) : null,
      finish: result ? parsePos(result.positionText) : null,
      positionText: result?.positionText ?? null,
      status: result?.status ?? null,
      points: (result ? Number(result.points) : 0) + (s ? Number(s.points) : 0),
      fastestLap: result?.FastestLap?.rank === "1",
      qualiPosition: q ? parsePos(q.position) : null,
      sprint: s
        ? { finish: parsePos(s.positionText), positionText: s.positionText, points: Number(s.points) }
        : null,
    };
  });
}

export function teammateOf(driverId: string, rows: DriverStandingRow[]): string | null {
  const me = rows.find((r) => r.Driver.driverId === driverId);
  if (!me) return null;
  const team = currentTeam(me);
  // The teammate with the most points, in case a substitute also drove the car.
  const others = rows
    .filter((r) => r.Driver.driverId !== driverId && currentTeam(r) === team)
    .sort((a, b) => Number(b.points) - Number(a.points));
  return others[0]?.Driver.driverId ?? null;
}

/**
 * Who beat whom, weekend by weekend.
 *
 * Race: only rounds where both started; a classified finish beats any non-finish; two
 * non-finishes are not counted. Qualifying: rounds where both set a position.
 */
export function headToHead(
  a: string,
  b: string,
  results: Race[],
  qualifying: Race[],
): HeadToHead {
  const race = { a: 0, b: 0, counted: 0 };
  for (const r of results) {
    const ra = r.Results?.find((x) => x.Driver.driverId === a);
    const rb = r.Results?.find((x) => x.Driver.driverId === b);
    if (!ra || !rb) continue;
    const fa = parsePos(ra.positionText);
    const fb = parsePos(rb.positionText);
    if (fa == null && fb == null) continue;
    race.counted += 1;
    if (fa == null) race.b += 1;
    else if (fb == null) race.a += 1;
    else if (fa < fb) race.a += 1;
    else race.b += 1;
  }

  const quali = { a: 0, b: 0, counted: 0 };
  for (const r of qualifying) {
    const qa = parsePos(r.QualifyingResults?.find((x) => x.Driver.driverId === a)?.position);
    const qb = parsePos(r.QualifyingResults?.find((x) => x.Driver.driverId === b)?.position);
    if (qa == null || qb == null) continue;
    quali.counted += 1;
    if (qa < qb) quali.a += 1;
    else quali.b += 1;
  }

  return { a, b, race, quali };
}

// ------------------------------------------------------------------ calendar

/** Start of the race as a Date; date-only entries are taken as midnight UTC. */
export function raceStart(race: Race): Date {
  return new Date(`${race.date}T${race.time ?? "00:00:00Z"}`);
}

export function nextRace(schedule: Race[], now: Date): Race | null {
  // A race counts as upcoming until three hours after lights-out.
  const grace = 3 * 3600 * 1000;
  return schedule.find((r) => raceStart(r).getTime() + grace > now.getTime()) ?? null;
}

export function ageAt(dateOfBirth: string, today: Date): number {
  const dob = new Date(dateOfBirth);
  let age = today.getUTCFullYear() - dob.getUTCFullYear();
  const beforeBirthday =
    today.getUTCMonth() < dob.getUTCMonth() ||
    (today.getUTCMonth() === dob.getUTCMonth() && today.getUTCDate() < dob.getUTCDate());
  if (beforeBirthday) age -= 1;
  return age;
}
