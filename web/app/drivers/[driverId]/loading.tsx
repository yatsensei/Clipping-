// A profile generates on its first visit, behind a rate-limited API; show the shape of
// the page rather than nothing while that happens.
export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6" aria-busy="true">
      <div className="h-3 w-24 rounded bg-panel-high" />
      <div className="h-36 animate-pulse rounded-lg border border-line bg-panel" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="h-96 animate-pulse rounded-lg border border-line bg-panel" />
        <div className="h-48 animate-pulse rounded-lg border border-line bg-panel" />
      </div>
    </main>
  );
}
