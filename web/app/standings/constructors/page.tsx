import type { Metadata } from "next";
import { StandingsExplorer } from "@/components/standings/StandingsExplorer";
import { loadStandings } from "@/lib/f1/queries";

export const metadata: Metadata = { title: "Constructors' standings" };

export const revalidate = 3600;

export default async function ConstructorStandingsPage() {
  const data = await loadStandings("constructors");
  return <StandingsExplorer data={data} />;
}
