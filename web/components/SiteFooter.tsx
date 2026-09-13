import Link from "next/link";

/**
 * One footer for the whole site. It names the data sources on every page because
 * nothing here is the site's own measurement: standings come from Jolpica-F1, images
 * from Wikimedia Commons, and every energy figure is model output.
 */
export function SiteFooter() {
  return (
    <footer className="border-t border-line px-4 py-8 text-[11px] leading-relaxed text-muted sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
        <p className="max-w-xl">
          Results and standings from{" "}
          <a
            href="https://api.jolpi.ca/"
            className="focus-ring text-ink underline-offset-2 hover:underline"
          >
            Jolpica-F1
          </a>
          . Energy deployment figures are model output from a physics simulation fitted
          to public telemetry — not measurements, and not any team&apos;s.
        </p>
        <nav className="flex gap-4" aria-label="Footer">
          <Link href="/credits" className="focus-ring hover:text-ink">
            Credits &amp; sources
          </Link>
          <a
            href="https://github.com/yatsensei/Clipping-"
            className="focus-ring hover:text-ink"
          >
            Source
          </a>
        </nav>
      </div>
    </footer>
  );
}
