import { EnergyExplainer } from "@/components/home/EnergyExplainer";
import { Hero } from "@/components/home/Hero";
import { LastRaceCard, NextRaceCard } from "@/components/home/RaceCards";
import type { Comparison, Geometry, Strategy } from "@/lib/api";
import { loadHome } from "@/lib/f1/queries";
import { serverApi } from "@/lib/server-data";

// Live standings and results, revalidated hourly. The energy figure beside them comes
// from the committed snapshot and never changes between builds.
export const revalidate = 3600;

const FEATURE_CIRCUIT = "monza";

export default async function Home() {
  const [home, energy] = await Promise.all([loadHome(), loadEnergy()]);

  return (
    <main className="mx-auto max-w-7xl space-y-10 px-4 py-10 sm:px-6 sm:py-14">
      <Hero drivers={home.drivers} constructors={home.constructors} progress={home.progress} />

      <section className="grid gap-4 md:grid-cols-2">
        <LastRaceCard race={home.lastRace} />
        <NextRaceCard race={home.nextRace} />
      </section>

      <EnergyExplainer {...energy} />
    </main>
  );
}

async function loadEnergy(): Promise<{
  geometry: Geometry | null;
  strategy: Strategy | null;
  comparison: Comparison | null;
}> {
  try {
    const [geometry, strategy, comparison] = await Promise.all([
      serverApi.geometry(FEATURE_CIRCUIT),
      serverApi.strategy(FEATURE_CIRCUIT, "optimal"),
      serverApi.comparison(FEATURE_CIRCUIT),
    ]);
    return { geometry, strategy, comparison };
  } catch {
    // The snapshot is optional here; the explainer still reads without the figure.
    return { geometry: null, strategy: null, comparison: null };
  }
}
