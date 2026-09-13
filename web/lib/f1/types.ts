/**
 * Jolpica-F1 (Ergast-compatible) response shapes, and the domain types the UI uses.
 *
 * Everything numeric in the raw API is a STRING — positions, points, rounds, grid slots.
 * The raw types say so honestly; the domain types below are what the pure functions in
 * ./standings.ts turn them into, and they are what components should consume.
 */

// ---------------------------------------------------------------------------- raw

export interface MRData<T> {
  MRData: { total: string; limit: string; offset: string } & T;
}

export interface JolpicaDriver {
  driverId: string;
  permanentNumber?: string;
  code?: string;
  url: string;
  givenName: string;
  familyName: string;
  dateOfBirth: string;
  nationality: string;
}

export interface JolpicaConstructor {
  constructorId: string;
  url: string;
  name: string;
  nationality: string;
}

export interface DriverStandingRow {
  position: string;
  positionText?: string;
  points: string;
  wins: string;
  Driver: JolpicaDriver;
  /** Every constructor driven for this season, in order; the last is the current team. */
  Constructors: JolpicaConstructor[];
}

export interface ConstructorStandingRow {
  position: string;
  positionText?: string;
  points: string;
  wins: string;
  Constructor: JolpicaConstructor;
}

export interface StandingsList<R> {
  season: string;
  round: string;
  DriverStandings?: R[];
  ConstructorStandings?: R[];
}

export interface StandingsTable<R> {
  StandingsTable: { season: string; round?: string; StandingsLists: StandingsList<R>[] };
}

export interface Circuit {
  circuitId: string;
  url: string;
  circuitName: string;
  Location: { lat: string; long: string; locality: string; country: string };
}

export interface Session {
  date: string;
  time?: string;
}

export interface RaceResultRow {
  number: string;
  /** Classification order, always numeric — even for retirements. */
  position: string;
  /** "R" retired, "D" disqualified, "W" withdrawn, "E" excluded, else the position. */
  positionText: string;
  points: string;
  grid: string;
  laps: string;
  status: string;
  Time?: { millis?: string; time: string };
  FastestLap?: { rank?: string; lap: string; Time: { time: string } };
  Driver: JolpicaDriver;
  Constructor: JolpicaConstructor;
}

export interface QualifyingRow {
  number: string;
  position: string;
  Q1?: string;
  Q2?: string;
  Q3?: string;
  Driver: JolpicaDriver;
  Constructor: JolpicaConstructor;
}

export interface Race {
  season: string;
  round: string;
  url: string;
  raceName: string;
  Circuit: Circuit;
  date: string;
  time?: string;
  FirstPractice?: Session;
  SecondPractice?: Session;
  ThirdPractice?: Session;
  Qualifying?: Session;
  Sprint?: Session;
  SprintQualifying?: Session;
  Results?: RaceResultRow[];
  QualifyingResults?: QualifyingRow[];
  SprintResults?: RaceResultRow[];
}

export interface RaceTable {
  RaceTable: { season: string; round?: string; Races: Race[] };
}

// ------------------------------------------------------------------------- domain

export type StandingsKind = "drivers" | "constructors";

/** One row of a championship table, the same shape for drivers and constructors. */
export interface StandingsRow {
  id: string;
  /** The constructor this row is coloured by. For a constructor row, its own id. */
  teamId: string;
  position: number;
  points: number;
  wins: number;
}

/** The table as it stood after a given round. */
export interface StandingsSnapshot {
  round: number;
  raceName: string | null;
  rows: StandingsRow[];
}

/** Who a row is: enough to render a name, an avatar and a profile link. */
export interface Entity {
  id: string;
  kind: StandingsKind;
  /** Display name: "Kimi Antonelli", "McLaren". */
  label: string;
  /** Three-letter code for drivers, a short name for teams. */
  short: string;
  teamId: string;
  number: string | null;
  nationality: string;
  /** Wikipedia article, from the API. */
  url: string;
  givenName?: string;
  familyName?: string;
  dateOfBirth?: string;
}

/** A driver's weekend, one row of a season results table. */
export interface DriverRoundRow {
  round: number;
  raceName: string;
  circuitId: string;
  country: string;
  date: string;
  /** null until the race has a result in the API. */
  raced: boolean;
  grid: number | null;
  /** Classified finishing position, or null for R/D/W/E. */
  finish: number | null;
  positionText: string | null;
  status: string | null;
  points: number;
  fastestLap: boolean;
  qualiPosition: number | null;
  sprint: { finish: number | null; positionText: string; points: number } | null;
}

export interface HeadToHead {
  a: string;
  b: string;
  race: { a: number; b: number; counted: number };
  quali: { a: number; b: number; counted: number };
}

export interface Progression {
  rounds: number[];
  raceNames: (string | null)[];
  ids: string[];
  /** Per id, one value per round; null before the entity first appears. */
  points: Record<string, (number | null)[]>;
  positions: Record<string, (number | null)[]>;
}
