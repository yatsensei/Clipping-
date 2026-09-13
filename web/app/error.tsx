"use client";

/**
 * Route-level boundary. The live pages depend on a third-party API at request time; when
 * it is down and there is no cached page to fall back on, say so rather than a blank.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-line bg-panel p-6">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted">Error</div>
        <h1 className="display mt-2 text-lg text-ink">Could not load this page</h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Live standings and results come from the Jolpica-F1 API. It did not answer, and
          there is no cached copy of this page yet.
        </p>
        {error.digest && (
          <p className="tabular mt-2 text-[10px] text-muted">ref {error.digest}</p>
        )}
        <button
          onClick={reset}
          className="focus-ring mt-5 rounded border border-line bg-panel-high px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-ink transition-colors hover:border-muted"
        >
          Try again
        </button>
      </div>
    </main>
  );
}
