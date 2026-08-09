import { promises as fs } from "node:fs";
import path from "node:path";
import {
  API_BASE,
  STATIC_MODE,
  paths,
  type CircuitListItem,
  type Comparison,
  type Geometry,
  type Meta,
  type Strategy,
} from "./api";

/**
 * Data access for SERVER components only.
 *
 * A server component cannot fetch a relative URL — there is no origin to resolve `/api`
 * against — so in static mode the snapshot is read straight off disk instead. That is
 * also strictly faster than an HTTP round trip to ourselves, and it lets the pages
 * prerender at build time with no server running.
 *
 * Import this from `page.tsx` and nothing else. Client components use `api` from
 * ./api, which fetches over HTTP.
 */

const SNAPSHOT = path.join(process.cwd(), "public", "api");

async function read<T>(relative: string): Promise<T> {
  if (!STATIC_MODE) {
    // Live API mode: the base is absolute, so a normal fetch works server-side.
    const res = await fetch(`${API_BASE}${relative}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`${relative} failed (${res.status})`);
    return (await res.json()) as T;
  }

  const file = path.join(SNAPSHOT, relative.replace(/^\//, ""));
  try {
    return JSON.parse(await fs.readFile(file, "utf8")) as T;
  } catch (cause) {
    throw new Error(
      `Missing snapshot ${relative}. Run \`uv run python -m scripts.export_static\` ` +
        `from the repository root to regenerate web/public/api.`,
      { cause },
    );
  }
}

export const serverApi = {
  circuits: () => read<CircuitListItem[]>(paths.circuits()),
  geometry: (id: string) => read<Geometry>(paths.geometry(id)),
  strategy: (id: string, mode: string) => read<Strategy>(paths.strategy(id, mode)),
  comparison: (id: string) => read<Comparison>(paths.comparison(id)),
  meta: () => read<Meta>(paths.meta()),
};
