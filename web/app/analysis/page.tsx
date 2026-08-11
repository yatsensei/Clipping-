import { Analysis } from "@/components/Analysis";
import { type CircuitListItem } from "@/lib/api";
import { serverApi } from "@/lib/server-data";

// Everything downstream is precomputed, so this prerenders at build time. There is
// nothing to revalidate on a schedule and no request-time work to do.
export default async function Page() {
  let circuits: CircuitListItem[] = [];
  let error: string | null = null;

  try {
    circuits = await serverApi.circuits();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || circuits.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface p-6">
        <div className="max-w-md rounded-lg border border-line bg-panel p-6">
          <h1 className="display text-lg text-ink">CLIPPING</h1>
          <p className="mt-3 text-sm text-deploy">No circuit data found.</p>
          <p className="mt-2 text-[11px] leading-relaxed text-muted">
            The site reads a snapshot of the API from <code>web/public/api</code>.
            Regenerate it from the repository root:
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-surface p-3 text-[11px] text-ink">
            uv run python -m scripts.export_static
          </pre>
          {error && (
            <p className="mt-3 text-[11px] text-muted">{error}</p>
          )}
        </div>
      </main>
    );
  }

  return <Analysis circuits={circuits} />;
}
