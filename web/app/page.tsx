import Link from "next/link";

// Placeholder until the homepage lands; keeps the build green through the restructure.
export default function Home() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
      <h1 className="display text-3xl text-ink">CLIPPING</h1>
      <p className="mt-4 max-w-lg font-sans text-sm leading-relaxed text-muted">
        Formula 1 analytics. Standings, profiles and a physics-based energy deployment
        optimiser for the 2026 regulations.
      </p>
      <Link
        href="/energy"
        className="focus-ring mt-8 inline-block rounded bg-deploy px-5 py-3 text-xs uppercase tracking-[0.18em] text-surface"
      >
        Energy deployment →
      </Link>
    </main>
  );
}
