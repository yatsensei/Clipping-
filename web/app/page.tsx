import { Analysis } from "@/components/Analysis";
import { api, type CircuitListItem } from "@/lib/api";

// The circuit list comes from the API at request time. Everything downstream is
// precomputed, so there is nothing to revalidate on a schedule.
export const dynamic = "force-dynamic";

export default async function Page() {
  let circuits: CircuitListItem[] = [];
  let error: string | null = null;

  try {
    circuits = await api.circuits();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (error || circuits.length === 0) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#08090A] p-6">
        <div className="max-w-md rounded-lg border border-[#262A30] bg-[#141619] p-6">
          <h1 className="display text-lg text-[#F2F0EB]">CLIPPING</h1>
          <p className="mt-3 text-sm text-[#FF2E17]">The API is not reachable.</p>
          <p className="mt-2 text-[11px] leading-relaxed text-[#6B7280]">
            Start it from the repository root:
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-[#08090A] p-3 text-[11px] text-[#F2F0EB]">
            uv run uvicorn api.main:app --reload
          </pre>
          {error && (
            <p className="mt-3 text-[11px] text-[#6B7280]">{error}</p>
          )}
        </div>
      </main>
    );
  }

  return <Analysis circuits={circuits} />;
}
