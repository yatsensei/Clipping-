import type { Metadata } from "next";
import { StandingsExplorer } from "@/components/standings/StandingsExplorer";
import { loadStandings } from "@/lib/f1/queries";

export const metadata: Metadata = { title: "Drivers' standings" };

// Rebuilt at most hourly; the data layer caches completed rounds for a week.
export const revalidate = 3600;

export default async function DriverStandingsPage() {
  const data = await loadStandings("drivers");
  return <StandingsExplorer data={data} />;
}
