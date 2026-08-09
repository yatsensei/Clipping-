import Link from "next/link";
import { Logo } from "@/components/Nav";
import { LapScroller } from "@/components/landing/LapScroller";
import { type Geometry, type Strategy } from "@/lib/api";
import { serverApi } from "@/lib/server-data";

// Monza. The taper problem is most visceral on a circuit that spends more than half its
// distance above 290 km/h, and the greedy strategy empties the store there inside two
// kilometres.
const LANDING_CIRCUIT = "monza";

export default async function Landing() {
  let geometry: Geometry | null = null;
  let greedy: Strategy | null = null;
  let error: string | null = null;

  try {
    [geometry, greedy] = await Promise.all([
      serverApi.geometry(LANDING_CIRCUIT),
      serverApi.strategy(LANDING_CIRCUIT, "greedy"),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (!geometry || !greedy) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md rounded-lg border border-[#262A30] bg-[#141619] p-6">
          <h1 className="display text-lg">CLIPPING</h1>
          <p className="mt-3 text-sm text-[#FF2E17]">No circuit data found.</p>
          <p className="mt-2 text-[11px] leading-relaxed text-[#6B7280]">
            The site reads a snapshot of the API from <code>web/public/api</code>.
            Regenerate it from the repository root:
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-[#08090A] p-3 text-[11px]">
            uv run python -m scripts.export_static
          </pre>
          {error && <p className="mt-3 text-[11px] text-[#6B7280]">{error}</p>}
        </div>
      </main>
    );
  }

  return (
    <main>
      {/* Not mix-blend-difference: the shader field runs underneath, and a blended
          header inverts unpredictably as the background warms and cools. */}
      <header className="fixed inset-x-0 top-0 z-20 flex items-center justify-between gap-4 px-5 py-3">
        <Logo />
        <Link
          href="/analysis"
          className="focus-ring rounded border border-[#262A30] bg-[#08090A]/70 px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-[#F2F0EB] backdrop-blur-md transition-colors hover:border-[#FF2E17]"
        >
          Skip to the analysis →
        </Link>
      </header>

      <LapScroller geometry={geometry} greedy={greedy} />

      <footer className="border-t border-[#262A30] px-5 py-10 text-[11px] leading-relaxed text-[#6B7280]">
        <div className="mx-auto max-w-7xl">
          <p className="max-w-2xl">
            Track geometry is derived from measured GPS across{" "}
            {geometry.provenance.laps_pooled} clean qualifying laps. Speed, deployment,
            state of charge and clipping are model output from a physics simulation
            fitted to real telemetry — public Formula 1 data contains no energy channels,
            so none of it is measured. Figures are for a generic 2026-specification car
            under stated assumptions, not any team&apos;s.
          </p>
          <p className="mt-3">
            {geometry.provenance.session} · reference lap{" "}
            {geometry.provenance.reference_driver}{" "}
            <span className="tabular">
              {geometry.provenance.reference_lap_time_s.toFixed(3)}s
            </span>
          </p>
        </div>
      </footer>
    </main>
  );
}
