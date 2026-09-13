export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6" aria-busy="true">
      <div className="h-3 w-24 rounded bg-panel-high" />
      <div className="h-36 animate-pulse rounded-lg border border-line bg-panel" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="h-24 animate-pulse rounded-lg border border-line bg-panel" />
        <div className="h-24 animate-pulse rounded-lg border border-line bg-panel" />
      </div>
      <div className="h-64 animate-pulse rounded-lg border border-line bg-panel" />
    </main>
  );
}
