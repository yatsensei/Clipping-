import { cache } from "react";
import type {
  ConstructorStandingRow,
  DriverStandingRow,
  MRData,
  Race,
  RaceTable,
  StandingsTable,
} from "./types";

/**
 * Server-only access to Jolpica-F1, the maintained successor to the Ergast API.
 *
 * Every call goes through `fetch` with `next.revalidate`, so Next's Data Cache — durable
 * and shared across serverless instances on Vercel — is the only cache. Nothing here is
 * memoised in module scope: that would be per-lambda, and the point is that Jolpica sees
 * one request per URL per TTL however many instances serve the site.
 *
 * Two constraints shape the design:
 *   - Jolpica answers 403 to requests without a descriptive User-Agent, and rate-limits
 *     at 4 req/s burst and 500 req/hour. A page render can want twenty URLs at once (one
 *     standings table per completed round), so calls are queued through a small limiter
 *     rather than fired in parallel.
 *   - Completed rounds are immutable, barring a stewards' appeal. They cache for a week;
 *     only the current round and season-wide endpoints refresh hourly.
 *
 * On final failure this THROWS. Under ISR an error during revalidation keeps the last
 * good page, and during `next build` it fails the build — both are the right outcome.
 */

if (typeof window !== "undefined") {
  throw new Error("lib/f1/jolpica is server-only; import it from server components");
}

export const JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1";
export const SEASON = 2026;

/** Seconds. */
export const TTL = {
  live: 3600,
  archive: 7 * 24 * 3600,
  schedule: 24 * 3600,
} as const;

const USER_AGENT =
  process.env.F1_USER_AGENT ??
  "clipping-f1-analytics/0.1 (https://github.com/yatsensei/Clipping-)";

const MAX_IN_FLIGHT = 4;
const MIN_SPACING_MS = 260;
const ATTEMPTS = 3;
const PAGE = 100;

export class JolpicaError extends Error {
  constructor(
    public readonly status: number,
    public readonly path: string,
  ) {
    super(`Jolpica ${status} on ${path}`);
    this.name = "JolpicaError";
  }
}

// ----------------------------------------------------------------- rate limiter

const queue: Array<() => void> = [];
let inFlight = 0;
let lastStart = 0;

function pump() {
  if (inFlight >= MAX_IN_FLIGHT || queue.length === 0) return;
  const wait = lastStart + MIN_SPACING_MS - Date.now();
  if (wait > 0) {
    setTimeout(pump, wait);
    return;
  }
  inFlight += 1;
  lastStart = Date.now();
  queue.shift()!();
}

function acquire(): Promise<() => void> {
  return new Promise((resolve) => {
    queue.push(() => {
      let released = false;
      resolve(() => {
        if (released) return;
        released = true;
        inFlight -= 1;
        pump();
      });
    });
    pump();
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function retryDelay(response: Response | null, attempt: number): number {
  const header = response?.headers.get("Retry-After");
  const seconds = header ? Number(header) : NaN;
  return Number.isFinite(seconds) ? seconds * 1000 : 500 * 2 ** attempt;
}

// ---------------------------------------------------------------------- fetch

/** GET one Jolpica path (e.g. `/2026/driverStandings.json`). */
export async function jolpica<T>(
  path: string,
  { revalidate }: { revalidate: number },
): Promise<T> {
  const url = `${JOLPICA_BASE}${path}`;
  let last: Response | null = null;

  for (let attempt = 0; attempt < ATTEMPTS; attempt += 1) {
    if (attempt > 0) await sleep(retryDelay(last, attempt - 1));

    const release = await acquire();
    try {
      last = await fetch(url, {
        headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
        next: { revalidate },
      });
    } catch {
      // Network failure: retry like a 5xx.
      last = null;
      continue;
    } finally {
      release();
    }

    if (last.ok) return (await last.json()) as T;
    if (last.status !== 429 && last.status < 500) break;
  }

  throw new JolpicaError(last?.status ?? 0, path);
}

/**
 * Walk a paginated endpoint. Jolpica paginates by ROW, not by race, so a race can be
 * split across two pages; callers merge with `mergeRaces`.
 */
export async function jolpicaAll<T extends MRData<unknown>>(
  path: string,
  opts: { revalidate: number },
): Promise<T[]> {
  const sep = path.includes("?") ? "&" : "?";
  const at = (offset: number) => `${path}${sep}limit=${PAGE}&offset=${offset}`;

  const first = await jolpica<T>(at(0), opts);
  const total = Number(first.MRData.total);
  const rest: Promise<T>[] = [];
  for (let offset = PAGE; offset < total; offset += PAGE) {
    rest.push(jolpica<T>(at(offset), opts));
  }
  return [first, ...(await Promise.all(rest))];
}

/**
 * Concatenate the per-race result arrays of pages that split a race.
 *
 * Pages cache independently, so after a new race lands page 1 can be an hour older
 * than page 3 and the boundary between them has moved. Rows are therefore de-duplicated
 * by driver within a race; a row missing for that hour is the lesser failure.
 */
export function mergeRaces(pages: MRData<RaceTable>[]): Race[] {
  const byRound = new Map<string, Race>();
  const keys = ["Results", "QualifyingResults", "SprintResults"] as const;
  type Row = { Driver: { driverId: string } };

  for (const page of pages) {
    for (const race of page.MRData.RaceTable.Races) {
      const existing = byRound.get(race.round);
      if (!existing) {
        byRound.set(race.round, { ...race });
        continue;
      }
      for (const key of keys) {
        const incoming = race[key] as Row[] | undefined;
        if (!incoming) continue;
        const current = (existing[key] ?? []) as Row[];
        const seen = new Set(current.map((r) => r.Driver.driverId));
        // The union of the three array types defeats a generic spread; assign per key.
        (existing as unknown as Record<string, unknown>)[key] = [
          ...current,
          ...incoming.filter((r) => !seen.has(r.Driver.driverId)),
        ];
      }
    }
  }
  return [...byRound.values()].sort((a, b) => Number(a.round) - Number(b.round));
}

// ---------------------------------------------------------------- endpoints
//
// Wrapped in React.cache so the layout, page and generateMetadata of one render share
// a single call. Across renders the Data Cache does the work.

export const getSchedule = cache(async (): Promise<Race[]> => {
  const data = await jolpica<MRData<RaceTable>>(`/${SEASON}.json?limit=50`, {
    revalidate: TTL.schedule,
  });
  return data.MRData.RaceTable.Races;
});

type DriverTable = MRData<StandingsTable<DriverStandingRow>>;
type ConstructorTable = MRData<StandingsTable<ConstructorStandingRow>>;

/** Current driver standings; `round` is the last round they include. */
export const getCurrentDriverStandings = cache(
  async (): Promise<{ round: number; rows: DriverStandingRow[] }> => {
    const data = await jolpica<DriverTable>(`/${SEASON}/driverStandings.json`, {
      revalidate: TTL.live,
    });
    const list = data.MRData.StandingsTable.StandingsLists[0];
    return { round: Number(list?.round ?? 0), rows: list?.DriverStandings ?? [] };
  },
);

export const getCurrentConstructorStandings = cache(
  async (): Promise<{ round: number; rows: ConstructorStandingRow[] }> => {
    const data = await jolpica<ConstructorTable>(
      `/${SEASON}/constructorStandings.json`,
      { revalidate: TTL.live },
    );
    const list = data.MRData.StandingsTable.StandingsLists[0];
    return { round: Number(list?.round ?? 0), rows: list?.ConstructorStandings ?? [] };
  },
);

export function ttlForRound(round: number, latest: number): number {
  return round < latest ? TTL.archive : TTL.live;
}

export async function getDriverStandingsAt(
  round: number,
  latest: number,
): Promise<DriverStandingRow[]> {
  const data = await jolpica<DriverTable>(`/${SEASON}/${round}/driverStandings.json`, {
    revalidate: ttlForRound(round, latest),
  });
  return data.MRData.StandingsTable.StandingsLists[0]?.DriverStandings ?? [];
}

export async function getConstructorStandingsAt(
  round: number,
  latest: number,
): Promise<ConstructorStandingRow[]> {
  const data = await jolpica<ConstructorTable>(
    `/${SEASON}/${round}/constructorStandings.json`,
    { revalidate: ttlForRound(round, latest) },
  );
  return data.MRData.StandingsTable.StandingsLists[0]?.ConstructorStandings ?? [];
}

/** Every completed round's driver table, 1..latest, in order. */
export const getDriverStandingsByRound = cache(
  async (): Promise<{ latest: number; rounds: DriverStandingRow[][] }> => {
    const { round: latest } = await getCurrentDriverStandings();
    const rounds = await Promise.all(
      Array.from({ length: latest }, (_, i) => getDriverStandingsAt(i + 1, latest)),
    );
    return { latest, rounds };
  },
);

export const getConstructorStandingsByRound = cache(
  async (): Promise<{ latest: number; rounds: ConstructorStandingRow[][] }> => {
    const { round: latest } = await getCurrentConstructorStandings();
    const rounds = await Promise.all(
      Array.from({ length: latest }, (_, i) => getConstructorStandingsAt(i + 1, latest)),
    );
    return { latest, rounds };
  },
);

export const getSeasonResults = cache(async (): Promise<Race[]> => {
  const pages = await jolpicaAll<MRData<RaceTable>>(`/${SEASON}/results.json`, {
    revalidate: TTL.live,
  });
  return mergeRaces(pages);
});

export const getSeasonQualifying = cache(async (): Promise<Race[]> => {
  const pages = await jolpicaAll<MRData<RaceTable>>(`/${SEASON}/qualifying.json`, {
    revalidate: TTL.live,
  });
  return mergeRaces(pages);
});

export const getSeasonSprints = cache(async (): Promise<Race[]> => {
  const pages = await jolpicaAll<MRData<RaceTable>>(`/${SEASON}/sprint.json`, {
    revalidate: TTL.live,
  });
  return mergeRaces(pages);
});

/** The most recent race with a classification, or null before the season starts. */
export const getLastRace = cache(async (): Promise<Race | null> => {
  const data = await jolpica<MRData<RaceTable>>(`/${SEASON}/last/results.json`, {
    revalidate: TTL.live,
  });
  return data.MRData.RaceTable.Races[0] ?? null;
});
