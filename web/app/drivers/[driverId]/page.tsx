import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { HeadToHeadBar } from "@/components/profile/HeadToHeadBar";
import { PositionSparkline } from "@/components/profile/PositionSparkline";
import { ProfileHeader } from "@/components/profile/ProfileHeader";
import { SeasonResultsTable } from "@/components/profile/SeasonResultsTable";
import { loadDriverProfile } from "@/lib/f1/queries";
import { ageAt } from "@/lib/f1/standings";
import { teamStyle } from "@/lib/teams";

// Generated on first visit and then revalidated hourly, rather than enumerated at
// build: the set of drivers is whoever the live standings say it is.
export const revalidate = 3600;
export const dynamicParams = true;
export async function generateStaticParams() {
  return [];
}

type Params = { params: Promise<{ driverId: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { driverId } = await params;
  const profile = await loadDriverProfile(driverId);
  // Decided here, not only in the page: metadata resolves before the loading boundary
  // starts streaming, so this is what makes an unknown id a real 404 status.
  if (!profile) notFound();
  return { title: profile.entity.label };
}

export default async function DriverPage({ params }: Params) {
  const { driverId } = await params;
  const profile = await loadDriverProfile(driverId);
  if (!profile) notFound();

  const { entity, standing, teammate, headToHead, rows, progression } = profile;
  const team = teamStyle(entity.teamId);
  const facts = [
    entity.number ? { label: "No.", value: entity.number } : null,
    { label: "Nationality", value: entity.nationality },
    entity.dateOfBirth
      ? { label: "Age", value: String(ageAt(entity.dateOfBirth, new Date())) }
      : null,
  ].filter((f): f is { label: string; value: string } => f != null);

  const raced = rows.filter((r) => r.raced);
  const podiums = raced.filter((r) => r.finish != null && r.finish <= 3).length;
  const poles = rows.filter((r) => r.qualiPosition === 1).length;
  const dnfs = raced.filter((r) => r.finish == null).length;
  const hasSprints = rows.some((r) => r.sprint);
  const entrants = progression.ids.length;

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
      <nav className="text-[11px] uppercase tracking-[0.16em] text-muted" aria-label="Breadcrumb">
        <Link href="/drivers" className="focus-ring hover:text-ink">
          Drivers
        </Link>
        <span className="mx-2" aria-hidden="true">/</span>
        <span className="text-ink">{entity.short}</span>
      </nav>

      <ProfileHeader entity={entity} standing={standing} facts={facts} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Starts" value={raced.length} />
            <Stat label="Podiums" value={podiums} />
            <Stat label="Poles" value={poles} />
            <Stat label="DNFs" value={dnfs} />
          </dl>
          <SeasonResultsTable rows={rows} hasSprints={hasSprints} />
        </div>

        <aside className="space-y-4">
          <PositionSparkline
            positions={progression.positions[entity.id] ?? []}
            rounds={progression.rounds}
            colour={team.colour}
            maxPosition={Math.max(entrants, 2)}
          />
          {teammate && headToHead && (
            <HeadToHeadBar subject={entity} other={teammate.entity} h2h={headToHead} />
          )}
          {teammate && (
            <Link
              href={`/drivers/${teammate.entity.id}`}
              className="focus-ring block rounded-lg border border-line bg-panel p-3 text-[11px] text-muted transition-colors hover:border-muted hover:text-ink"
            >
              Teammate: <span className="font-sans text-sm text-ink">{teammate.entity.label}</span>
              {teammate.standing && (
                <span className="tabular ml-2">
                  P{teammate.standing.position} · {teammate.standing.points} pts
                </span>
              )}
            </Link>
          )}
          <a
            href={entity.url}
            className="focus-ring block text-[11px] text-muted underline-offset-2 hover:text-ink hover:underline"
          >
            Wikipedia →
          </a>
        </aside>
      </div>
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
