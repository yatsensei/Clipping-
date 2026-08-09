/**
 * Typed client for the strategy API.
 *
 * The types mirror api/schemas.py. Two fields matter more than they look:
 * `data_type` distinguishes measured geometry from simulated telemetry, and
 * `repeatable` marks a lap that ended with less energy than it started. Both are
 * rendered, never dropped — a modelled number presented as a measurement, or a greedy
 * lap time presented without its energy debt, would be the interface lying.
 */

/**
 * Two modes.
 *
 * STATIC (the default, and what ships): the API's payloads are snapshotted to
 * web/public/api by scripts/export_static.py and served as files. Every endpoint in this
 * project is a pure reader — nothing is computed on request — so the service is not
 * needed in production, and the site deploys with no backend at all.
 *
 * LIVE: set NEXT_PUBLIC_API_BASE to run against the FastAPI service instead, which is
 * useful while changing the API itself.
 *
 * Static files cannot serve query strings, so `?mode=optimal` becomes
 * `/strategy/optimal.json`.
 */
const LIVE_BASE = process.env.NEXT_PUBLIC_API_BASE;
export const STATIC_MODE = !LIVE_BASE;
export const API_BASE = LIVE_BASE ?? "/api";

export type StrategyMode = "optimal" | "uniform" | "greedy";

/** The brief's "naive" is this codebase's "uniform"; snapshots use canonical names. */
export function canonicalMode(mode: string): StrategyMode {
  return (mode === "naive" ? "uniform" : mode) as StrategyMode;
}

export const paths = {
  circuits: () => (STATIC_MODE ? "/circuits.json" : "/circuits"),
  meta: () => (STATIC_MODE ? "/meta.json" : "/meta"),
  detail: (id: string) =>
    STATIC_MODE ? `/circuits/${id}.json` : `/circuits/${id}`,
  geometry: (id: string) =>
    STATIC_MODE ? `/circuits/${id}/geometry.json` : `/circuits/${id}/geometry`,
  comparison: (id: string) =>
    STATIC_MODE
      ? `/circuits/${id}/comparison.json`
      : `/circuits/${id}/comparison`,
  strategy: (id: string, mode: string) =>
    STATIC_MODE
      ? `/circuits/${id}/strategy/${canonicalMode(mode)}.json`
      : `/circuits/${id}/strategy?mode=${encodeURIComponent(mode)}`,
};

export interface Provenance {
  session: string;
  data_year: number;
  is_fallback: boolean;
  reference_driver: string;
  reference_team: string;
  reference_lap_time_s: number;
  laps_pooled: number;
  gps_samples: number;
  note: string;
  fallback_note: string | null;
}

export interface CircuitListItem {
  circuit_id: string;
  event_name: string;
  location: string;
  country: string;
  round_number: number;
  event_date: string;
  lap_distance_m: number;
  corner_count: number;
  official_corner_count: number;
  longest_straight_m: number;
  data_year: number;
  is_fallback: boolean;
  provenance: string;
  reference_driver: string;
  reference_lap_time_s: number;
  has_strategy: boolean;
}

export interface Segment {
  kind: "corner" | "straight";
  start_m: number;
  end_m: number;
  length_m: number;
  min_radius_m: number;
  mean_radius_m: number;
  apex_m: number | null;
}

export interface Geometry {
  circuit_id: string;
  step_m: number;
  lap_distance_m: number;
  distance_m: number[];
  x_m: number[];
  y_m: number[];
  z_m: number[];
  curvature_1_per_m: number[];
  gradient: number[];
  segments: Segment[];
  official_corners: { number: number; letter: string; distance_m: number }[];
  provenance: Provenance;
  data_type: "measured_gps_derived";
}

export interface Strategy {
  circuit_id: string;
  mode: StrategyMode;
  requested_mode: string;
  lap_time_s: number;
  distance_m: number[];
  speed_kph: number[];
  deploy_kw: number[];
  harvest_kw: number[];
  soc_mj: number[];
  clipping: boolean[];
  deploy_fraction: number[];
  soc_start_mj: number;
  energy_deployed_mj: number;
  repeatable: boolean;
  repeatability_note: string | null;
  provenance: Provenance;
  data_type: "model_output";
}

export interface StrategySummary {
  mode: string;
  lap_time_s: number;
  energy_deployed_mj: number;
  energy_harvested_mj: number | null;
  clipping_pct: number;
  repeatable: boolean;
  soc_end_mj: number;
}

export interface LearnedPolicyScore {
  gain_retained_pct: number;
  lap_time_s: number;
  periodic: boolean;
  comparable: boolean;
}

export interface Comparison {
  circuit_id: string;
  soc_start_mj: number;
  harvest_cap_mj: number;
  baseline: "uniform";
  baseline_statement: string;
  gain_vs_uniform_s: number;
  gain_vs_greedy_s: number;
  greedy_energy_debt_mj: number;
  greedy_caveat: string;
  strategies: StrategySummary[];
  learned_policy: LearnedPolicyScore | null;
  provenance: Provenance;
  data_type: "model_output";
}

export interface Meta {
  regulations: {
    source: string;
    published: string;
    url: string;
    energy_store_window_mj: number;
    harvest_cap_mj: number;
    harvest_cap_basis: string;
  };
  vehicle: {
    fitted: Record<string, number | null>;
    assumed: Record<string, number | null>;
    assumptions: string[];
    power_identifiable: boolean | null;
  };
  simulation_accuracy: {
    circuits: number;
    mean_speed_rmse_kph: number;
    mean_abs_lap_error_s: number;
    note: string;
  } | null;
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* response was not JSON; keep the status text */
    }
    throw new ApiError(`${path} failed (${res.status}): ${detail}`, res.status);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const api = {
  circuits: () => get<CircuitListItem[]>(paths.circuits()),
  geometry: (id: string) => get<Geometry>(paths.geometry(id)),
  strategy: (id: string, mode: string) => get<Strategy>(paths.strategy(id, mode)),
  comparison: (id: string) => get<Comparison>(paths.comparison(id)),
  meta: () => get<Meta>(paths.meta()),
};

export const MODE_LABEL: Record<StrategyMode, string> = {
  optimal: "Optimal",
  uniform: "Uniform",
  greedy: "Greedy",
};

export const MODE_DESCRIPTION: Record<StrategyMode, string> = {
  optimal: "Dynamic programming solution, energy-neutral over the lap",
  uniform: "Constant deployment, chosen so the lap is energy-neutral",
  greedy: "Deploy everything available — empties the store and cannot be repeated",
};
