import { polyline } from "@/lib/chart";
import { TOKENS } from "@/lib/track";

/**
 * Championship position after each round, first place at the top. Server-rendered SVG;
 * the team colour comes in as a stroke so the same component serves drivers and teams.
 */
export function PositionSparkline({
  positions,
  rounds,
  colour,
  maxPosition,
}: {
  positions: (number | null)[];
  rounds: number[];
  colour: string;
  /** The bottom of the axis — number of entrants. */
  maxPosition: number;
}) {
  const W = 1000;
  const H = 120;
  const PAD = 10;
  const n = positions.length;
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * W : W / 2);
  const y = (p: number) => PAD + ((p - 1) / Math.max(maxPosition - 1, 1)) * (H - 2 * PAD);
  const d = polyline(positions.map((p, i) => (p == null ? null : [x(i), y(p)])));
  const last = [...positions].reverse().find((p) => p != null);
  const lastIndex = positions.length - 1 - [...positions].reverse().findIndex((p) => p != null);
  const ticks = [1, Math.ceil(maxPosition / 2), maxPosition];

  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
          Championship position by round
        </span>
        {last != null && (
          <span className="tabular text-xs text-ink">
            P{last}
            <span className="ml-1 text-muted">now</span>
          </span>
        )}
      </div>
      <div className="relative" style={{ height: H }}>
        <div className="pointer-events-none absolute inset-y-0 left-0 w-6" aria-hidden="true">
          {ticks.map((t) => (
            <span
              key={t}
              className="tabular absolute right-1 -translate-y-1/2 text-[9px] leading-none text-muted"
              style={{ top: y(t) }}
            >
              {t}
            </span>
          ))}
        </div>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="absolute inset-y-0 right-0"
          style={{ left: 24, width: "calc(100% - 24px)", height: H }}
          role="img"
          aria-label={`Championship position after each of ${n} rounds`}
        >
          {ticks.map((t) => (
            <line
              key={t}
              x1={0}
              y1={y(t)}
              x2={W}
              y2={y(t)}
              stroke={TOKENS.line}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
              opacity={0.65}
            />
          ))}
          <path
            d={d}
            fill="none"
            stroke={colour}
            strokeWidth={2}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
          {last != null && (
            <circle
              cx={x(lastIndex)}
              cy={y(last)}
              r={4}
              fill={colour}
              stroke={TOKENS.panel}
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>
      <div
        className="tabular mt-1 flex justify-between text-[9px] text-muted"
        style={{ marginLeft: 24 }}
        aria-hidden="true"
      >
        {rounds.map((r) => (
          <span key={r}>{r}</span>
        ))}
      </div>
    </div>
  );
}
