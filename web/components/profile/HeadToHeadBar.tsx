import type { Entity, HeadToHead } from "@/lib/f1/types";
import { teamVars } from "@/lib/teams";

/**
 * Teammate comparison: who finished ahead in qualifying and in the race, weekend by
 * weekend. Both share a team colour, so the two sides are told apart by weight — the
 * subject is solid, the teammate is the wash — rather than by hue.
 */
export function HeadToHeadBar({
  subject,
  other,
  h2h,
}: {
  subject: Entity;
  other: Entity;
  h2h: HeadToHead;
}) {
  // `h2h.a` is whoever was passed first to headToHead(); map to the subject.
  const flip = h2h.a !== subject.id;
  const pick = (s: { a: number; b: number; counted: number }) =>
    flip ? { me: s.b, them: s.a, n: s.counted } : { me: s.a, them: s.b, n: s.counted };

  return (
    <div className="rounded-lg border border-line bg-panel p-3" style={teamVars(subject.teamId)}>
      <div className="flex items-baseline justify-between px-1 pb-2">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted">
          Head-to-head vs {other.short}
        </span>
        <span className="text-[10px] text-muted">
          {subject.short} <span aria-hidden="true">■</span> · {other.short}{" "}
          <span aria-hidden="true">□</span>
        </span>
      </div>
      <div className="space-y-3">
        <Bar label="Qualifying" {...pick(h2h.quali)} />
        <Bar label="Race" {...pick(h2h.race)} />
      </div>
    </div>
  );
}

function Bar({ label, me, them, n }: { label: string; me: number; them: number; n: number }) {
  const pct = n > 0 ? (me / n) * 100 : 50;
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="uppercase tracking-[0.14em] text-muted">{label}</span>
        <span className="tabular text-ink">
          {me}
          <span className="mx-1 text-muted">–</span>
          {them}
          {n === 0 && <span className="ml-2 text-muted">no shared weekends yet</span>}
        </span>
      </div>
      <div
        className="team-wash mt-1 h-2 overflow-hidden rounded-full"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={n}
        aria-valuenow={me}
        aria-label={`${label}: ahead ${me} of ${n}`}
      >
        <div className="team-bar h-full rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
