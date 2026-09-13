import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { EntityCard } from "@/components/profile/EntityCard";
import { HeadToHeadBar } from "@/components/profile/HeadToHeadBar";
import { PositionSparkline } from "@/components/profile/PositionSparkline";
import { ProfileHeader } from "@/components/profile/ProfileHeader";
import { TeamResultsTable } from "@/components/profile/TeamResultsTable";
import { ProgressionChart } from "@/components/standings/ProgressionChart";
import { loadTeamProfile } from "@/lib/f1/queries";
import { teamStyle } from "@/lib/teams";

export const revalidate = 3600;
export const dynamicParams = true;
export async function generateStaticParams() {
  return [];
}

type Params = { params: Promise<{ constructorId: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { constructorId } = await params;
  const profile = await loadTeamProfile(constructorId);
  // See drivers/[driverId]: a 404 status has to be decided before streaming starts.
  if (!profile) notFound();
  return { title: profile.entity.label };
}

export default async function TeamPage({ params }: Params) {
  const { constructorId } = await params;
  const profile = await loadTeamProfile(constructorId);
  if (!profile) notFound();

  const { entity, standing, drivers, headToHead, progression } = profile;
  const team = teamStyle(entity.teamId);
  const allRows = drivers.flatMap((d) => d.rows.filter((r) => r.raced));
  const wins = allRows.filter((r) => r.finish === 1).length;
  const podiums = allRows.filter((r) => r.finish != null && r.finish <= 3).length;
  const poles = drivers.flatMap((d) => d.rows).filter((r) => r.qualiPosition === 1).length;
  const dnfs = allRows.filter((r) => r.finish == null).length;

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
      <nav className="text-[11px] uppercase tracking-[0.16em] text-muted" aria-label="Breadcrumb">
        <Link href="/teams" className="focus-ring hover:text-ink">
          Teams
        </Link>
        <span className="mx-2" aria-hidden="true">/</span>
        <span className="text-ink">{team.short || entity.label}</span>
      </nav>

      <ProfileHeader
        entity={entity}
        standing={standing}
        facts={[
          { label: "Base", value: entity.nationality },
          { label: "Drivers", value: drivers.map((d) => d.entity.short).join(" · ") || "—" },
        ]}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        {drivers.map((d) => (
          <EntityCard
            key={d.entity.id}
            entity={d.entity}
            standing={d.standing}
            href={`/drivers/${d.entity.id}`}
            subtitle={d.entity.number ? `No. ${d.entity.number} · ${d.entity.nationality}` : d.entity.nationality}
          />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Wins" value={wins} />
            <Stat label="Podiums" value={podiums} />
            <Stat label="Poles" value={poles} />
            <Stat label="DNFs" value={dnfs} />
          </dl>
          {drivers.length > 0 && <TeamResultsTable drivers={drivers} />}
        </div>

        <aside className="space-y-4">
          <PositionSparkline
            positions={progression.positions[entity.id] ?? []}
            rounds={progression.rounds}
            colour={team.colour}
            maxPosition={Math.max(progression.ids.length, 2)}
          />
          {drivers.length >= 2 && headToHead && (
            <HeadToHeadBar subject={drivers[0].entity} other={drivers[1].entity} h2h={headToHead} />
          )}
          <a
            href={entity.url}
            className="focus-ring block text-[11px] text-muted underline-offset-2 hover:text-ink hover:underline"
          >
            Wikipedia →
          </a>
        </aside>
      </div>

      <ProgressionChart
        progression={progression}
        entities={profile.teamEntities}
        highlight={[entity.id]}
        cursor={progression.rounds.length - 1}
      />
    </main>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <dt className="text-[10px] uppercase tracking-[0.16em] text-muted">{label}</dt>
      <dd className="tabular mt-1 text-xl text-ink">{value}</dd>
    </div>
  );
}
