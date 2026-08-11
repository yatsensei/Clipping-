import type { Strategy } from "@/lib/api";

/**
 * The narrative beats, anchored to where they actually happen.
 *
 * Nothing here is a hardcoded distance. Each beat is located by searching the greedy
 * strategy's own traces for the moment it describes, so the copy cannot drift away from
 * the data — if the model changes, the story moves with it.
 *
 * Greedy is the right strategy to narrate: the landing page exists to show the PROBLEM.
 * At Monza it empties the store inside the first two kilometres and then clips for most
 * of the lap, which is exactly the sequence the reader needs to feel before the app
 * offers to solve it.
 */

export interface Beat {
  id: string;
  /** Fraction of the lap, 0..1, where this beat sits. */
  at: number;
  kicker: string;
  title: string;
  body: string;
  /** Optional figure pulled from the data. */
  readout?: { label: string; value: string };
}

const TAPER_KPH = 290;
/** Minimum share of the lap each beat must advance the car. ~260 m at Monza. */
const MIN_SEPARATION = 0.045;

/**
 * Scroll progress to lap position, piecewise-linear through the beats.
 *
 * A straight scroll-to-distance map does not work, because the events are not evenly
 * spread around the lap: at Monza the store empties and the car begins clipping within
 * 15 m of each other, 1.2 km in. Mapped linearly, three narrative sections would fire
 * inside 0.3% of the page while the reader still had four screens to scroll, and the
 * copy would describe somewhere the car had long since left.
 *
 * Giving each beat an equal share of scroll keeps the two in step. Scroll position is
 * still lap distance and still strictly monotonic — it advances through the dense part
 * of the story more slowly, the way a camera would.
 */
export function lapFractionForScroll(progress: number, knots: number[]): number {
  if (knots.length < 2) return progress;
  const clamped = Math.min(Math.max(progress, 0), 1);
  const scaled = clamped * (knots.length - 1);
  const i = Math.min(Math.floor(scaled), knots.length - 2);
  return knots[i] + (knots[i + 1] - knots[i]) * (scaled - i);
}

/** Which beat owns this scroll position. */
export function activeBeatForScroll(progress: number, count: number): number {
  if (count <= 1) return 0;
  const clamped = Math.min(Math.max(progress, 0), 1);
  return Math.min(count - 1, Math.max(0, Math.round(clamped * (count - 1))));
}

function firstIndex(pred: (i: number) => boolean, n: number, from = 0): number {
  for (let i = from; i < n; i++) if (pred(i)) return i;
  return -1;
}

export function buildBeats(greedy: Strategy, lapDistanceM: number): Beat[] {
  const n = greedy.speed_kph.length;
  const frac = (i: number) => (i < 0 ? 0 : i / (n - 1));
  const metres = (i: number) => ((i / (n - 1)) * lapDistanceM).toFixed(0);

  // The lap array starts at the timing line, which at Monza is mid-straight at 330 km/h
  // with a full store — so a naive search finds "deployment begins" and "the taper bites"
  // both at index 0 and the story collapses. Anchor instead at the slowest point of the
  // lap, the tightest corner, and read the sequence forward from there: brake, turn,
  // deploy out of the corner, hit the taper, run dry, clip.
  let slowest = 0;
  for (let i = 1; i < n; i++) {
    if (greedy.speed_kph[i] < greedy.speed_kph[slowest]) slowest = i;
  }

  const deployAt = firstIndex((i) => greedy.deploy_kw[i] > 50, n, slowest);
  const taperAt = firstIndex(
    (i) => greedy.speed_kph[i] > TAPER_KPH,
    n,
    Math.max(deployAt, slowest),
  );
  const emptyAt = firstIndex((i) => greedy.soc_mj[i] < 0.02, n, slowest);
  const clipAt = firstIndex((i) => greedy.clipping[i], n, slowest);

  const clipCount = greedy.clipping.filter(Boolean).length;
  const clipPct = (100 * clipCount) / n;
  const topSpeed = Math.max(...greedy.speed_kph);

  const beats: Beat[] = [
    {
      id: "open",
      at: 0,
      kicker: "Monza · lap distance",
      title: "Scroll is distance.",
      body:
        "Everything below happens somewhere on this lap. As you scroll, the car moves " +
        "along the real GPS trace of a qualifying lap, and the background carries the " +
        "state of its battery. This is the naive strategy: deploy whatever you have, " +
        "whenever you have it.",
    },
    {
      id: "deploy",
      at: frac(deployAt),
      kicker: `${metres(deployAt)} m`,
      title: "Deployment begins.",
      body:
        "Out of the first chicane the driver asks for everything. 350 kW of electrical " +
        "power on top of the combustion engine, and the car leaves the corner hard. " +
        "Nothing about this feels like a mistake yet.",
      readout: { label: "Electrical power", value: "350 kW" },
    },
    {
      id: "taper",
      at: frac(taperAt),
      kicker: `${metres(taperAt)} m`,
      title: "The taper bites at 290 km/h.",
      body:
        "The 2026 regulations throttle electrical deployment as speed rises. Full power " +
        "is available to 290 km/h, then it falls away, reaching zero at 345. Energy " +
        "spent up here buys less and less speed — it is being taken away faster than it " +
        "can be used.",
      readout: { label: "Available at 340 km/h", value: "100 kW of 350" },
    },
    {
      id: "empty",
      at: frac(emptyAt),
      kicker: `${metres(emptyAt)} m`,
      title: "The store is empty.",
      body:
        "Less than two kilometres into the lap the battery is flat. There are still " +
        "three straights to come, and every one of them will now be taken on combustion " +
        "power alone.",
      readout: { label: "State of charge", value: "0.00 MJ" },
    },
    {
      id: "clip",
      at: frac(clipAt),
      kicker: `${metres(clipAt)} m`,
      title: "Flat out, and losing time.",
      body:
        "This is clipping. The throttle is wide open, the driver is doing nothing wrong, " +
        "and the car is slower than it should be because there is no electrical power " +
        "left to give. On this lap it happens across most of the distance.",
      readout: {
        label: "Lap spent clipping",
        value: `${clipPct.toFixed(0)}%`,
      },
    },
    {
      id: "release",
      at: 1,
      kicker: "the question",
      title: "So where should it have gone?",
      body:
        "A fixed budget of energy, spent around a lap, where the value of a joule " +
        "depends entirely on where you spend it. That has an optimal answer, and it is " +
        "worth roughly two and a half seconds a lap. This is the tool that finds it.",
      readout: { label: "Top speed reached", value: `${topSpeed.toFixed(0)} km/h` },
    },
  ];

  // Beats must advance monotonically, and a search that found nothing returns 0. Drop
  // any beat that would sit before the one preceding it rather than tell the story out
  // of order.
  const ordered: Beat[] = [];
  let last = -1;
  for (const beat of beats) {
    if (beat.at >= last) {
      ordered.push(beat);
      last = beat.at;
    }
  }
  return spaceOut(ordered);
}

/**
 * Guarantee every beat moves the car a visible distance.
 *
 * The events genuinely cluster: at Monza the taper crossing, the store emptying and the
 * onset of clipping happen within 15 m of each other, 1.2 km into the lap. Mapping scroll
 * straight onto those positions gave three consecutive full-height sections that together
 * advanced the car by 0.3% of the lap — which reads, correctly, as the animation being
 * stuck.
 *
 * Each beat is therefore pushed to sit at least MIN_SEPARATION of a lap after the one
 * before it. A beat still marks where its section BEGINS, so the car is at the stated
 * distance as you arrive at the text and travels on while you read it. The kickers keep
 * the true measured distance, because that is where the event actually happens.
 */
function spaceOut(beats: Beat[]): Beat[] {
  const n = beats.length;
  if (n < 2) return beats;

  const at = beats.map((b) => b.at);

  // Forward: push each beat clear of its predecessor.
  for (let i = 1; i < n; i++) {
    at[i] = Math.max(at[i], at[i - 1] + MIN_SEPARATION);
  }

  // The last beat releases into the app at the end of the lap; pin it and walk back so
  // nothing gets shoved past it.
  at[n - 1] = 1;
  for (let i = n - 2; i >= 0; i--) {
    at[i] = Math.min(at[i], at[i + 1] - MIN_SEPARATION);
  }
  at[0] = Math.max(0, at[0]);

  return beats.map((beat, i) => ({ ...beat, at: at[i] }));
}
