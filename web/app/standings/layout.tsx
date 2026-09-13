import { SubNav } from "@/components/SubNav";

export default function StandingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] text-deploy">2026</div>
          <h1 className="display mt-1 text-2xl text-ink sm:text-3xl">Championship standings</h1>
        </div>
        <SubNav
          label="Championship"
          links={[
            { href: "/standings/drivers", label: "Drivers" },
            { href: "/standings/constructors", label: "Constructors" },
          ]}
        />
      </div>
      <div className="mt-6">{children}</div>
    </main>
  );
}
