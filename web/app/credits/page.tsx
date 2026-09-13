import type { Metadata } from "next";
import Image from "next/image";
import { MEDIA, mediaUrl, type MediaCredit } from "@/lib/media";
import { teamStyle } from "@/lib/teams";

export const metadata: Metadata = { title: "Credits & sources" };

/**
 * Where everything comes from. Static: the manifest is imported at build time, and the
 * data sources do not change between builds.
 */
export default function CreditsPage() {
  const drivers = entries(MEDIA.drivers);
  const teams = entries(MEDIA.teams);
  const missing = Object.keys(MEDIA.missing);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 font-sans sm:px-6">
      <h1 className="display text-2xl text-ink sm:text-3xl">Credits &amp; sources</h1>

      <section className="mt-8">
        <h2 className="text-[10px] uppercase tracking-[0.24em] text-deploy">Data</h2>
        <dl className="mt-3 divide-y divide-line rounded-lg border border-line bg-panel text-sm">
          <Source
            name="Jolpica-F1"
            href="https://api.jolpi.ca/"
            what="Race results, qualifying, sprints, schedules and championship standings. The community-maintained successor to the Ergast API. Standings refresh hourly; completed rounds are cached for a week."
          />
          <Source
            name="FastF1"
            href="https://docs.fastf1.dev/"
            what="Public car telemetry and GPS used to build circuit geometry and fit the vehicle model behind the energy-deployment optimiser. Contains no energy channels: every deployment and state-of-charge figure on this site is model output."
          />
          <Source
            name="FIA 2026 Power Unit Technical Regulations"
            href="https://www.fia.com/regulation/category/110"
            what="Deployment power, the speed taper, the energy store window and the harvest caps."
          />
          <Source
            name="OpenF1"
            href="https://openf1.org/"
            what="The broadcast team colours used throughout, transcribed once rather than fetched."
          />
          <Source
            name="Wikimedia Commons"
            href="https://commons.wikimedia.org/"
            what="Driver portraits and team logos, under the licences listed below. Anyone without a freely licensed image is shown as initials."
          />
        </dl>
      </section>

      <section className="mt-10">
        <h2 className="text-[10px] uppercase tracking-[0.24em] text-deploy">Driver portraits</h2>
        <CreditList kind="drivers" items={drivers} />
      </section>

      <section className="mt-10">
        <h2 className="text-[10px] uppercase tracking-[0.24em] text-deploy">Team logos</h2>
        <CreditList kind="teams" items={teams} />
        {missing.length > 0 && (
          <p className="mt-3 text-[11px] leading-relaxed text-muted">
            No freely licensed image was available for{" "}
            {missing.map((id) => teamStyle(id).name || id).join(", ")}; they are shown
            as initials on the team colour.
          </p>
        )}
      </section>

      {MEDIA.generated && (
        <p className="mt-10 text-[11px] text-muted">
          Images last fetched {MEDIA.generated.slice(0, 10)} by{" "}
          <code>scripts/fetch_media.py</code>.
        </p>
      )}
    </main>
  );
}

function entries(map: Record<string, MediaCredit | null>): [string, MediaCredit][] {
  return Object.entries(map).filter((e): e is [string, MediaCredit] => e[1] != null);
}

function Source({ name, href, what }: { name: string; href: string; what: string }) {
  return (
    <div className="grid gap-1 p-4 sm:grid-cols-[180px_1fr] sm:gap-4">
      <dt>
        <a href={href} className="focus-ring text-ink underline-offset-2 hover:underline">
          {name}
        </a>
      </dt>
      <dd className="leading-relaxed text-muted">{what}</dd>
    </div>
  );
}

function CreditList({ kind, items }: { kind: "drivers" | "teams"; items: [string, MediaCredit][] }) {
  if (items.length === 0) {
    return <p className="mt-3 text-sm text-muted">None fetched yet.</p>;
  }
  return (
    <ul className="mt-3 grid gap-2 sm:grid-cols-2">
      {items.map(([id, c]) => (
        <li key={id} className="flex gap-3 rounded-lg border border-line bg-panel p-3 text-[11px]">
          <span
            className={`relative h-12 w-12 shrink-0 overflow-hidden ${
              kind === "drivers" ? "rounded-full" : "rounded-md bg-[#f4f4f1] p-1"
            }`}
          >
            <Image
              src={mediaUrl(c)}
              alt=""
              width={96}
              height={96}
              unoptimized={c.file.endsWith(".svg")}
              className={`h-full w-full ${kind === "drivers" ? "object-cover" : "object-contain"}`}
            />
          </span>
          <span className="min-w-0 leading-relaxed text-muted">
            <a
              href={c.source_url}
              className="focus-ring block truncate text-ink underline-offset-2 hover:underline"
              title={c.title}
            >
              {c.title.replace(/^File:/, "")}
            </a>
            {c.author && <span className="block truncate">{c.author}</span>}
            <span className="block">
              {c.license_url ? (
                <a href={c.license_url} className="focus-ring underline-offset-2 hover:underline">
                  {c.license}
                </a>
              ) : (
                c.license
              )}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
