import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-line bg-panel p-6">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted">404</div>
        <h1 className="display mt-2 text-lg text-ink">Nothing here</h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          No page at this address. Driver and team pages exist only for entrants in the
          current championship standings.
        </p>
        <div className="mt-5 flex flex-wrap gap-3 text-[11px] uppercase tracking-[0.16em]">
          <Link href="/" className="focus-ring text-ink hover:text-deploy">
            Home
          </Link>
          <Link href="/standings/drivers" className="focus-ring text-muted hover:text-ink">
            Standings
          </Link>
          <Link href="/energy" className="focus-ring text-muted hover:text-ink">
            Energy deployment
          </Link>
        </div>
      </div>
    </main>
  );
}
