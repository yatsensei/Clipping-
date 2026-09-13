import Link from "next/link";
import type { Comparison, Geometry, Strategy } from "@/lib/api";
import { TOKENS, colourFor, project, strokeFor } from "@/lib/track";

/**
 * The energy-deployment problem in plain language, with the optimiser's own Monza lap
 * drawn beside it. The numbers are the regulations' and the model's, and the model's
 * are labelled as such: none of this is measured.
 */
export function EnergyExplainer({
  geometry,
  strategy,
  comparison,
}: {
  geometry: Geometry | null;
  strategy: Strategy | null;
  comparison: Comparison | null;
}) {
  return (
    <section className="grid gap-8 rounded-lg border border-line bg-panel p-5 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center">
      <div className="font-sans">
        <div className="text-[10px] uppercase tracking-[0.28em] text-deploy">
          Feature · Energy deployment
        </div>
        <h2 className="display mt-3 text-2xl leading-tight text-ink sm:text-3xl">
          Where should a 2026 car spend its battery?
        </h2>
        <div className="mt-4 space-y-3 text-sm leading-relaxed text-muted">
          <p>
            From 2026 nearly half a Formula 1 car&apos;s power is electric: a{" "}
            <b className="text-ink">350 kW</b> motor fed by a battery that holds{" "}
            <b className="text-ink">4 MJ</b> of usable energy — about eleven seconds at
            full power. Braking refills it, but only up to{" "}
            <b className="text-ink">7 MJ</b> per qualifying lap, and above{" "}
            <b className="text-ink">290 km/h</b> the rules taper the motor&apos;s
            power away until it reaches zero at 345 km/h.
          </p>
          <p>
            So the battery is worth most where the car is slow, and worth nothing on the
            end of the straight — but a lap has more corners than the battery has energy.
            Choosing where to deploy, where to harvest, and where to let the store run
            down is an optimisation problem, and the naive answer — deploy whenever you
            can — runs dry inside two kilometres at Monza.
          </p>
          <p>
            This site solves it by dynamic programming over a physics model fitted to
            real telemetry, then checks whether a learned policy can reproduce the
            answer on circuits it has never seen.
            {comparison && (
              <>
                {" "}
                At Monza the optimum is worth{" "}
                <b className="tabular text-ink">
                  {comparison.gain_vs_uniform_s.toFixed(3)} s
                </b>{" "}
                a lap over deploying at a constant rate.
              </>
            )}
          </p>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact label="MGU-K" value="350" unit="kW" />
          <Fact label="Store" value="4" unit="MJ" />
          <Fact label="Harvest cap" value="7" unit="MJ / lap" />
          <Fact label="Taper to zero" value="345" unit="km/h" />
        </dl>
        <div className="mt-6 flex flex-wrap gap-3 text-[11px] uppercase tracking-[0.18em]">
          <Link
            href="/energy"
            className="focus-ring rounded bg-deploy px-5 py-3 text-surface transition-opacity hover:opacity-90"
          >
            Scroll the lap →
          </Link>
          <Link
            href="/energy/analysis"
            className="focus-ring rounded border border-line px-5 py-3 text-ink transition-colors hover:border-deploy"
          >
            Open the analysis
          </Link>
        </div>
      </div>

      {geometry && strategy ? (
        <TrackFigure geometry={geometry} strategy={strategy} />
      ) : (
        <div className="hidden lg:block" />
      )}
    </section>
  );
}

function Fact({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <dt className="text-[9px] uppercase tracking-[0.18em] text-muted">{label}</dt>
      <dd className="tabular mt-0.5 text-lg text-ink">
        {value}
        <span className="ml-1 text-[10px] text-muted">{unit}</span>
      </dd>
    </div>
  );
}

/** The optimal Monza lap coloured by state, the same encoding as the analysis map. */
function TrackFigure({ geometry, strategy }: { geometry: Geometry; strategy: Strategy }) {
  const p = project(geometry, 1000, 40);
  const n = p.points.length;
  // Batch consecutive samples with the same colour into one path each.
  const segments: { colour: string; width: number; d: string }[] = [];
  for (let i = 0; i < n; i += 1) {
    const j = (i + 1) % n;
    const colour = colourFor(strategy.deploy_kw[i], strategy.harvest_kw[i], strategy.clipping[i]);
    const width = strokeFor(strategy.deploy_kw[i], strategy.harvest_kw[i], strategy.clipping[i]);
    const last = segments[segments.length - 1];
    const move = `L${p.points[j].x.toFixed(1)},${p.points[j].y.toFixed(1)}`;
    if (last && last.colour === colour && last.width === width) {
      last.d += ` ${move}`;
    } else {
      segments.push({
        colour,
        width,
        d: `M${p.points[i].x.toFixed(1)},${p.points[i].y.toFixed(1)} ${move}`,
      });
    }
  }
  return (
    <figure className="mx-auto w-full max-w-md">
      <svg
        viewBox={`0 0 ${p.width} ${p.height}`}
        className="h-auto w-full"
        role="img"
        aria-label="Monza, coloured by where the optimiser deploys, harvests and coasts"
      >
        <path d={p.path} fill="none" stroke={TOKENS.line} strokeWidth={9} strokeLinejoin="round" opacity={0.6} />
        {segments.map((s, k) => (
          <path
            key={k}
            d={s.d}
            fill="none"
            stroke={s.colour}
            strokeWidth={s.width}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[10px] uppercase tracking-[0.14em] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-4 rounded-full bg-deploy" /> deploy
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-4 rounded-full bg-harvest" /> harvest
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-4 rounded-full bg-line" /> coast
        </span>
        <span>Monza · optimal · model output</span>
      </figcaption>
    </figure>
  );
}
