import { describe, expect, it } from "vitest";
import { mergeRaces } from "./jolpica";
import {
  ageAt,
  constructorEntities,
  currentTeam,
  driverEntities,
  driverSeasonRows,
  gapToLeader,
  headToHead,
  nextRace,
  parsePos,
  positionDeltas,
  progression,
  teammateOf,
  toSnapshot,
} from "./standings";
import type {
  ConstructorStandingRow,
  DriverStandingRow,
  MRData,
  RaceTable,
  StandingsTable,
} from "./types";

// Real API captures (scripts/capture_fixtures.py). The assertions are invariants of the
// data's shape and of the functions, not of who is leading the championship.
import scheduleJson from "./__fixtures__/schedule.json";
import r14Drivers from "./__fixtures__/round-14-driverStandings.json";
import r13Drivers from "./__fixtures__/round-13-driverStandings.json";
import r1Drivers from "./__fixtures__/round-1-driverStandings.json";
import r14Teams from "./__fixtures__/round-14-constructorStandings.json";
import r13Teams from "./__fixtures__/round-13-constructorStandings.json";
import resultsP1 from "./__fixtures__/results-p1.json";
import qualifyingP1 from "./__fixtures__/qualifying-p1.json";
import sprintP1 from "./__fixtures__/sprint-p1.json";

type DT = MRData<StandingsTable<DriverStandingRow>>;
type CT = MRData<StandingsTable<ConstructorStandingRow>>;
const drivers = (j: unknown) =>
  (j as DT).MRData.StandingsTable.StandingsLists[0].DriverStandings!;
const teams = (j: unknown) =>
  (j as CT).MRData.StandingsTable.StandingsLists[0].ConstructorStandings!;
const races = (j: unknown) => mergeRaces([j as MRData<RaceTable>]);

const schedule = (scheduleJson as MRData<RaceTable>).MRData.RaceTable.Races;
const d14 = drivers(r14Drivers);
const d13 = drivers(r13Drivers);
const d1 = drivers(r1Drivers);
const results = races(resultsP1);
const qualifying = races(qualifyingP1);
const sprints = races(sprintP1);

describe("parsePos", () => {
  it("reads classified positions and rejects retirement codes", () => {
    expect(parsePos("1")).toBe(1);
    expect(parsePos("17")).toBe(17);
    expect(parsePos("R")).toBeNull();
    expect(parsePos("D")).toBeNull();
    expect(parsePos(undefined)).toBeNull();
    expect(parsePos("0")).toBeNull();
  });
});

describe("toSnapshot", () => {
  it("converts every field to a number and sorts by position", () => {
    const snap = toSnapshot("drivers", 14, "Spanish Grand Prix", d14);
    expect(snap.rows).toHaveLength(d14.length);
    for (const [i, row] of snap.rows.entries()) {
      expect(row.position).toBe(i + 1);
      expect(Number.isFinite(row.points)).toBe(true);
      expect(Number.isInteger(row.wins)).toBe(true);
      expect(row.teamId).not.toBe("");
    }
  });

  it("colours a driver by the LAST constructor listed — a mid-season move", () => {
    const moved = d14.find((r) => r.Constructors.length > 1);
    expect(moved, "fixture should contain a driver who changed team").toBeDefined();
    const last = moved!.Constructors[moved!.Constructors.length - 1].constructorId;
    expect(currentTeam(moved!)).toBe(last);
    const snap = toSnapshot("drivers", 14, null, d14);
    expect(snap.rows.find((r) => r.id === moved!.Driver.driverId)?.teamId).toBe(last);
  });

  it("handles constructor rows with the same shape", () => {
    const snap = toSnapshot("constructors", 14, null, teams(r14Teams));
    expect(snap.rows[0].position).toBe(1);
    expect(snap.rows[0].teamId).toBe(snap.rows[0].id);
  });
});

describe("positionDeltas", () => {
  it("is zero-sum-ish and matches a manual diff of two real rounds", () => {
    const cur = toSnapshot("drivers", 14, null, d14).rows;
    const prev = toSnapshot("drivers", 13, null, d13).rows;
    const deltas = positionDeltas(cur, prev);
    for (const row of cur) {
      const before = prev.find((p) => p.id === row.id);
      if (!before) {
        expect(deltas[row.id]).toBeNull();
      } else {
        expect(deltas[row.id]).toBe(before.position - row.position);
      }
    }
    // Someone moving up means someone else moved down.
    const sum = Object.values(deltas).reduce<number>((s, d) => s + (d ?? 0), 0);
    expect(sum).toBe(0);
  });

  it("works identically for constructors", () => {
    const cur = toSnapshot("constructors", 14, null, teams(r14Teams)).rows;
    const prev = toSnapshot("constructors", 13, null, teams(r13Teams)).rows;
    const deltas = positionDeltas(cur, prev);
    expect(Object.keys(deltas)).toHaveLength(cur.length);
    expect(Object.values(deltas).every((d) => d !== null)).toBe(true);
  });

  it("returns null for everyone with no previous round", () => {
    const cur = toSnapshot("drivers", 1, null, d1).rows;
    const deltas = positionDeltas(cur, null);
    expect(Object.values(deltas).every((d) => d === null)).toBe(true);
  });
});

describe("gapToLeader", () => {
  it("gives the leader zero and everyone else a non-negative gap", () => {
    const rows = toSnapshot("drivers", 14, null, d14).rows;
    const gaps = gapToLeader(rows);
    expect(gaps[rows[0].id]).toBe(0);
    expect(Object.values(gaps).every((g) => g >= 0)).toBe(true);
  });
});

describe("progression", () => {
  it("builds one column per round and nulls before an entrant appears", () => {
    const snaps = [
      toSnapshot("drivers", 1, "A", d1),
      toSnapshot("drivers", 13, "B", d13),
      toSnapshot("drivers", 14, "C", d14),
    ];
    const prog = progression(snaps);
    expect(prog.rounds).toEqual([1, 13, 14]);
    for (const id of prog.ids) {
      expect(prog.points[id]).toHaveLength(3);
      expect(prog.positions[id]).toHaveLength(3);
    }
    // Ordered by final position.
    const finalPos = prog.ids.map((id) => prog.positions[id][2] ?? Infinity);
    expect([...finalPos].sort((a, b) => a - b)).toEqual(finalPos);
    // Points never decrease round on round for anyone present throughout.
    for (const id of prog.ids) {
      const p = prog.points[id];
      if (p.every((v) => v != null)) {
        expect(p[1]!).toBeGreaterThanOrEqual(p[0]!);
        expect(p[2]!).toBeGreaterThanOrEqual(p[1]!);
      }
    }
  });
});

describe("entities", () => {
  it("builds a driver entity with code, number and team", () => {
    const e = driverEntities(d14);
    const lead = d14[0].Driver.driverId;
    expect(e[lead].label).toBe(`${d14[0].Driver.givenName} ${d14[0].Driver.familyName}`);
    expect(e[lead].short).toHaveLength(3);
    expect(e[lead].teamId).toBe(currentTeam(d14[0]));
  });

  it("builds constructor entities and applies short names", () => {
    const e = constructorEntities(teams(r14Teams), { mclaren: { name: "McLaren", short: "McL" } });
    expect(e.mclaren?.short).toBe("McL");
    expect(e.mclaren?.label).toBe("McLaren");
    expect(Object.keys(e)).toHaveLength(11);
  });
});

describe("mergeRaces", () => {
  it("joins a race split across pages without duplicating rows", () => {
    const page = resultsP1 as MRData<RaceTable>;
    const last = page.MRData.RaceTable.Races[page.MRData.RaceTable.Races.length - 1];
    // Simulate page 2 re-serving two rows of the split race plus new ones.
    const page2: MRData<RaceTable> = {
      MRData: {
        total: page.MRData.total,
        limit: "100",
        offset: "100",
        RaceTable: {
          season: "2026",
          Races: [
            {
              ...last,
              Results: [
                ...last.Results!.slice(-2),
                { ...last.Results![0], Driver: { ...last.Results![0].Driver, driverId: "zz" } },
              ],
            },
          ],
        },
      },
    };
    const merged = mergeRaces([page, page2]);
    const race = merged.find((r) => r.round === last.round)!;
    const ids = race.Results!.map((r) => r.Driver.driverId);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("zz");
    expect(race.Results).toHaveLength(last.Results!.length + 1);
  });
});

describe("driverSeasonRows", () => {
  it("returns one row per scheduled round, raced or not, with parsed fields", () => {
    const id = d14[0].Driver.driverId;
    const rows = driverSeasonRows(id, schedule, results, qualifying, sprints);
    expect(rows).toHaveLength(schedule.length);
    const raced = rows.filter((r) => r.raced);
    expect(raced.length).toBeGreaterThan(0);
    for (const r of raced) {
      expect(r.grid == null || r.grid >= 0).toBe(true);
      expect(r.finish == null || r.finish >= 1).toBe(true);
      expect(r.points).toBeGreaterThanOrEqual(0);
    }
    // A weekend with no race result can still carry sprint points (Saturday evening).
    const unraced = rows.filter((r) => !r.raced);
    for (const r of unraced) {
      expect(r.finish).toBeNull();
      expect(r.points).toBe(r.sprint?.points ?? 0);
    }
  });

  it("marks a retirement as unclassified but keeps the status text", () => {
    const retired = results
      .flatMap((r) => r.Results!.map((x) => ({ round: Number(r.round), x })))
      .find(({ x }) => x.positionText === "R");
    expect(retired, "fixture should contain a retirement").toBeDefined();
    const rows = driverSeasonRows(
      retired!.x.Driver.driverId,
      schedule,
      results,
      qualifying,
      sprints,
    );
    const row = rows.find((r) => r.round === retired!.round)!;
    expect(row.finish).toBeNull();
    expect(row.positionText).toBe("R");
    expect(row.status).toBe(retired!.x.status);
  });

  it("adds sprint points into the weekend total", () => {
    const sprintRace = sprints[0];
    const winner = sprintRace.SprintResults![0];
    const rows = driverSeasonRows(
      winner.Driver.driverId,
      schedule,
      results,
      qualifying,
      sprints,
    );
    const row = rows.find((r) => r.round === Number(sprintRace.round))!;
    expect(row.sprint?.points).toBe(Number(winner.points));
    expect(row.points).toBeGreaterThanOrEqual(Number(winner.points));
  });
});

describe("teammateOf / headToHead", () => {
  it("finds a teammate on the same current constructor", () => {
    const id = d14[0].Driver.driverId;
    const mate = teammateOf(id, d14);
    expect(mate).not.toBeNull();
    const mateRow = d14.find((r) => r.Driver.driverId === mate)!;
    expect(currentTeam(mateRow)).toBe(currentTeam(d14[0]));
  });

  it("counts every double-start exactly once", () => {
    const id = d14[0].Driver.driverId;
    const mate = teammateOf(id, d14)!;
    const h2h = headToHead(id, mate, results, qualifying);
    expect(h2h.race.a + h2h.race.b).toBe(h2h.race.counted);
    expect(h2h.quali.a + h2h.quali.b).toBe(h2h.quali.counted);
    expect(h2h.race.counted).toBeLessThanOrEqual(results.length);
    expect(h2h.quali.counted).toBeLessThanOrEqual(qualifying.length);
  });
});

describe("calendar", () => {
  it("picks the first race that has not finished", () => {
    const first = schedule[0];
    const before = new Date(`${first.date}T00:00:00Z`);
    expect(nextRace(schedule, before)?.round).toBe(first.round);
    const afterAll = new Date("2027-01-01T00:00:00Z");
    expect(nextRace(schedule, afterAll)).toBeNull();
  });

  it("computes age correctly either side of a birthday", () => {
    expect(ageAt("2000-06-15", new Date("2026-06-14T00:00:00Z"))).toBe(25);
    expect(ageAt("2000-06-15", new Date("2026-06-15T00:00:00Z"))).toBe(26);
  });
});
