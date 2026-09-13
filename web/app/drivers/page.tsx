import type { Metadata } from "next";
import { EntityCard } from "@/components/profile/EntityCard";
import { loadStandings } from "@/lib/f1/queries";

export const metadata: Metadata = { title: "Drivers" };
export const revalidate = 3600;

export default async function DriversPage() {
  const { snapshots, entities } = await loadStandings("drivers");
  const latest = snapshots[snapshots.length - 1];
  const rows = latest?.rows ?? [];

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="text-[10px] uppercase tracking-[0.28em] text-deploy">2026</div>
      <h1 className="display mt-1 text-2xl text-ink sm:text-3xl">Drivers</h1>
      <p className="mt-2 max-w-xl font-sans text-sm text-muted">
        Everyone classified in this season&apos;s championship, in championship order.
      </p>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((row) => {
          const e = entities[row.id];
          if (!e) return null;
          return (
            <EntityCard key={row.id} entity={e} standing={row} href={`/drivers/${row.id}`} />
          );
        })}
      </div>
    </main>
  );
}
