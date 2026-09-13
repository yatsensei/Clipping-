# Clipping

**A Formula 1 analytics site, and the physics underneath it.**

Live 2026 championship standings you can scrub round by round, a profile for every
driver and team, and the feature the project began as: a physics-informed optimiser
that computes the lap-time-optimal electrical deployment strategy for every circuit on
the calendar, built on real telemetry, with an interactive visualiser that animates the
result.

| Section | Route | Data |
|---|---|---|
| Home | `/` | live standings, last and next race |
| Standings | `/standings/drivers`, `/standings/constructors` | live, every round |
| Profiles | `/drivers/[id]`, `/teams/[id]` | live results, qualifying, head-to-head |
| Energy deployment | `/energy`, `/energy/analysis` | committed model output |
| Credits | `/credits` | image licences and data sources |

The sections below are about the optimiser, which is where the engineering is.

---

## Why this exists

The 2026 regulations rewrote Formula 1's power unit. The MGU-H — which recovered energy
from exhaust heat — was removed entirely. In its place, the MGU-K, which recovers energy
under braking, was upgraded from 120 kW to 350 kW. The result is a roughly 50:50 split
between combustion and electrical power.

That change created a problem drivers did not previously have to think about this hard.

Electrical deployment is capped by speed. A car gets full electrical power up to
290 km/h. Above that, deployment tapers away. Energy spent at the very top of a straight
is therefore largely wasted — it arrives exactly where the regulations are throttling it
away.

Meanwhile, the battery is small relative to how fast 350 kW drains it. Deploy greedily and
it empties before the lap's most valuable corner exits. When that happens the driver is at
full throttle and still losing time, because the car is running on combustion power alone.
Teams call this *clipping*. Harvesting deliberately at the end of straights to refill the
battery — accepting a small loss where deployment was tapering anyway — is called *super
clipping*.

So deployment stopped being "use it whenever you have it." It became a constrained
allocation problem: a fixed energy budget, spent across a lap, where the value of a joule
depends entirely on where you spend it. That problem has an optimal solution, and this
project finds it.

## Results

The optimiser gains **1.98 s per lap on average** over uniform constant deployment,
ranging from +1.15 s at Monaco to +2.63 s at Suzuka. Both strategies are held to the
same constraint: the lap must end with at least the energy it started with, or it is not
a strategy, it is a one-off.

An earlier version of this table reported 2.35 s. The difference is not the optimiser:
it is that the baselines used to be timed on a second simulator that did not feed an
empty battery back into the speed, so uniform was slower than it should have been and
greedy faster. Everything is now timed on one physics (see below), and the gain is what
survives that.

<!-- RESULTS:START -->

### Lap time gained, per circuit

Measured against **uniform constant deployment** at the same starting state of charge, both strategies required to end the lap with at least the energy they began with. All times in seconds.

| Circuit | Uniform | Optimal | **Gain** | Greedy | Greedy debt | Optimal clipping | Greedy clipping |
|---|---:|---:|---:|---:|---:|---:|---:|
| suzuka | 87.959 | 85.324 | **+2.634** | 86.421 | −1.37 MJ | 0% | 62% |
| silverstone | 88.648 | 86.181 | **+2.467** | 87.160 | −1.09 MJ | 0% | 59% |
| spa-francorchamps | 105.395 | 102.945 | **+2.450** | 104.271 | −1.24 MJ | 0% | 62% |
| shanghai | 92.726 | 90.326 | **+2.400** | 91.206 | −1.20 MJ | 0% | 53% |
| las-vegas | 94.583 | 92.202 | **+2.381** | 93.274 | −0.90 MJ | 0% | 66% |
| monza | 82.857 | 80.694 | **+2.163** | 81.255 | −1.18 MJ | 0% | 71% |
| montreal | 73.601 | 71.483 | **+2.117** | 71.632 | −1.26 MJ | 0% | 55% |
| yas-marina | 89.671 | 87.563 | **+2.108** | 88.085 | −1.17 MJ | 0% | 48% |
| spielberg | 67.816 | 65.722 | **+2.093** | 66.203 | −1.27 MJ | 0% | 54% |
| miami-gardens | 87.673 | 85.615 | **+2.059** | 86.622 | −0.71 MJ | 0% | 51% |
| lusail | 89.335 | 87.288 | **+2.047** | 88.197 | −1.37 MJ | 0% | 48% |
| baku | 106.715 | 104.810 | **+1.905** | 105.222 | −1.47 MJ | 0% | 52% |
| melbourne | 79.377 | 77.482 | **+1.895** | 77.859 | −1.44 MJ | 0% | 65% |
| austin | 97.024 | 95.169 | **+1.855** | 95.391 | −1.27 MJ | 0% | 43% |
| marina-bay | 91.219 | 89.383 | **+1.837** | 89.848 | −1.19 MJ | 0% | 41% |
| sao-paulo | 71.107 | 69.349 | **+1.757** | 70.007 | −1.16 MJ | 0% | 52% |
| mexico-city | 74.611 | 72.921 | **+1.689** | 73.109 | −1.31 MJ | 0% | 44% |
| barcelona | 74.057 | 72.455 | **+1.602** | 73.086 | −1.35 MJ | 0% | 53% |
| zandvoort | 76.805 | 75.320 | **+1.486** | 75.663 | −1.30 MJ | 0% | 41% |
| budapest | 76.917 | 75.488 | **+1.429** | 75.929 | −1.22 MJ | 0% | 36% |
| monte-carlo | 68.736 | 67.581 | **+1.154** | 67.868 | −1.02 MJ | 0% | 22% |
| **mean** | | | **+1.978** | | −1.21 MJ | 0% | 51% |

Greedy is timed on the same physics as the optimiser, so its clipping costs the time it really costs. It ends every lap in energy debt and is not repeatable, which is why it is not the baseline; where it is faster than uniform it is spending charge it never repays.

### Learned policy — leave-one-circuit-out

| Held-out circuit | DP gain | Model gain | Retained | Repeatable |
|---|---:|---:|---:|:--:|
| baku | +1.905 s | +2.436 s | 128% | **no** |
| spielberg | +2.093 s | +2.477 s | 118% | **no** |
| spa-francorchamps | +2.450 s | +2.755 s | 112% | **no** |
| sao-paulo | +1.757 s | +1.816 s | 103% | **no** |
| melbourne | +1.895 s | +1.892 s | 100% | **no** |
| monza | +2.163 s | +2.154 s | 100% | **no** |
| silverstone | +2.467 s | +2.426 s | 98% | **no** |
| suzuka | +2.634 s | +2.526 s | 96% | **no** |
| montreal | +2.117 s | +1.897 s | 90% | yes |
| miami-gardens | +2.059 s | +1.765 s | 86% | **no** |
| shanghai | +2.400 s | +2.055 s | 86% | yes |
| barcelona | +1.602 s | +1.347 s | 84% | yes |
| mexico-city | +1.689 s | +1.313 s | 78% | yes |
| las-vegas | +2.381 s | +1.776 s | 75% | **no** |
| zandvoort | +1.486 s | +0.933 s | 63% | yes |
| austin | +1.855 s | +1.124 s | 61% | yes |
| yas-marina | +2.108 s | +1.246 s | 59% | yes |
| marina-bay | +1.837 s | +1.032 s | 56% | yes |
| lusail | +2.047 s | +1.119 s | 55% | yes |
| monte-carlo | +1.154 s | +0.050 s | 4% | yes |
| budapest | +1.429 s | -0.093 s | -6% | yes |

Mean across all 21 folds: **78%**. On the 11 folds that produced a repeatable lap: **57%** (median 61%, best 90%).

Scores above 100% are not the model beating the optimiser. The DP is optimal subject to periodicity, and the only way past it is to break that constraint — every fold above 100% ends the lap with less charge than it started.

| Model | All folds | Repeatable laps only | Repeatable | Mean MAE |
|---|---:|---:|---:|---:|
| `gbm` | 78% | 57% | 11/21 | 0.14 |
| `gbm_reg` | 60% | 26% | 7/21 | 0.20 |
| `linear` | -74% | -128% | 8/21 | 0.33 |
| `always-deploy` | 70% | — | 0/21 | 0.95 |

### Physics model accuracy

The driver's deployment is reconstructed from the measured qualifying lap by inverse dynamics and replayed through the model, on the circuits with 2026 telemetry. One track grip factor per circuit is fitted so the replayed lap matches the measured time — the error before that fit is shown — and everything else is then measured, not fitted. Unexplained energy is what the lap needed that the modelled engine plus the tapered MGU-K could not have supplied.

| Circuit | Driver | Grip factor | Lap error before it | Speed RMSE | Speed bias | vmax error | Unexplained energy |
|---|---|---:|---:|---:|---:|---:|---:|
| barcelona | RUS | 1.09 | +2.55 s | 14.6 km/h | -1.4 km/h | -6.3 km/h | 0.22 MJ |
| budapest | HAM | 1.00 | -0.06 s | 8.1 km/h | -0.8 km/h | -3.0 km/h | 0.07 MJ |
| melbourne | RUS | 1.17 | +4.37 s | 15.8 km/h | +0.9 km/h | -0.8 km/h | 0.04 MJ |
| miami-gardens | ANT | 1.04 | +0.93 s | 13.0 km/h | -0.4 km/h | -3.9 km/h | 0.81 MJ |
| monte-carlo | VER | 1.19 | +5.10 s | 19.7 km/h | -2.6 km/h | +4.0 km/h | 0.00 MJ |
| montreal | ANT | 1.03 | +0.53 s | 8.8 km/h | +0.7 km/h | -1.7 km/h | 0.11 MJ |
| shanghai | ANT | 1.27 | +6.67 s | 22.8 km/h | +2.5 km/h | -0.8 km/h | 0.36 MJ |
| silverstone | ANT | 1.01 | +0.25 s | 11.8 km/h | -0.4 km/h | +0.6 km/h | 0.00 MJ |
| spa-francorchamps | LEC | 1.06 | +2.15 s | 19.5 km/h | -0.1 km/h | -4.5 km/h | 0.30 MJ |
| spielberg | ANT | 1.04 | +0.73 s | 19.0 km/h | -0.1 km/h | -1.6 km/h | 0.05 MJ |
| suzuka | RUS | 1.23 | +12.39 s | 22.3 km/h | -0.7 km/h | -1.5 km/h | 0.20 MJ |
| **mean** | | 1.10 | **3.25 s abs** | **15.9 km/h** | -0.2 km/h | -1.8 km/h | 0.20 MJ |

### Fitted vehicle parameters

| Parameter | Value | Basis |
|---|---:|---|
| Cd·A, high-drag state | 0.968 m² | fitted — 95% CI [0.954, 0.981], 29,275 straight-line coasting samples |
| Cd·A, straight-line state | 0.906 m² | **bound** — the most drag the car can have at terminal speed; true value in [0.761, 0.906] |
| Cl·A | 5.586 m² | fitted — lateral-acceleration envelope |
| μ lateral | 1.753 | fitted |
| μ braking | 1.386 | fitted |
| Lateral ceiling | 44.4 m/s² | fitted — tyre saturation, 4.5 g |
| Off-throttle force | 1197 N | fitted — engine braking plus MGU-K regen |
| Crr | 0.012 | **assumed** — not identifiable (see below) |
| ICE power | 400 kW | **assumed** — published figure; the smallest engine that closes each measured lap's energy budget has a median of ~410 kW |
| Driveline efficiency | 0.95 | **assumed** |
| Regen efficiency | 0.90 | **assumed** — no energy channels exist to measure it |
| Store-to-motor efficiency | 0.95 | **assumed** — the 350 kW cap is at the MGU-K output |
| Track grip factor | 1.00–1.27 | **fitted per 2026 circuit** to the measured lap time; 1.00 elsewhere |
| Mass | 778 kg | 768 kg regulatory minimum + 10 kg assumed qualifying fuel |

<!-- RESULTS:END -->

## Two corrections to the published figures

Both were found by checking the FIA regulations directly rather than trusting secondary
sources, and both change the model materially.

**The deployment taper reaches zero at 345 km/h, not 355.** Article 5.4.8 defines it
piecewise, and 355 km/h is the zero point for *override* mode, not normal running:

```
P(kW) = 1800 − 5·v      v < 340        →  the 350 kW cap binds up to 290 km/h
P(kW) = 6900 − 20·v     340 ≤ v < 345  →  100 kW at the knee
P(kW) = 0               v ≥ 345
```

The widely repeated "290 to 355 km/h" figure joins the start of the normal-mode taper to
the end of the override-mode one. The real curve is steeper.

**The qualifying harvest cap is 7 MJ, not 8.5 MJ.** Article 5.4.10's 8.5 MJ is the race
figure; for 2026 the FIA lowered qualifying, which is what this project simulates. It
binds on 12 of 21 circuits, so the distinction is not academic.

A third figure the brief left unspecified turned out to matter more than either: Article
5.4.9 caps the state-of-charge window at **4 MJ**, which is what makes the battery small
enough for the whole problem to exist.

## What is real, and what is modelled

This is the important section. Public Formula 1 telemetry contains **no energy channels at
all** — no state of charge, no deployment, no harvest. This was verified, not assumed: a
scan of every column across car, position, lap and merged telemetry for a 2026 session
found nothing.

| | Source |
|---|---|
| Track geometry, curvature, corner positions | **Measured.** GPS from clean qualifying laps, pooled across 64–281 laps per circuit |
| Speed, throttle, brake traces | **Measured.** FastF1, ~4 Hz |
| Air density | **Measured.** Computed per circuit from session weather |
| Cd·A (high-drag state), Cl·A, grip coefficients, off-throttle force | **Fitted** to measured telemetry |
| Cd·A (straight-line state) | **Bounded** from terminal-speed running; the bound is used |
| Track grip factor | **Fitted per 2026 circuit** to the measured lap time |
| ICE power, driveline, regen and store efficiencies, Crr | **Assumed.** Not identifiable — see below |
| The driver's deployment ("measured" mode) | **Inferred** from the measured speed by inverse dynamics under the model |
| Deployment, state of charge, harvest, clipping | **Model output.** Nothing here is measured |
| Lap times and gains | **Model output** |

Every API response carries a `data_type` field marking which of these it is, and the
interface renders that distinction rather than hiding it.

### The driver's own lap

The force balance runs both ways. Given the measured speed along a lap, the electrical
power the observed acceleration required beyond the engine is what the driver deployed,
and the recoverable share of the observed braking is what was harvested. That
reconstruction is served as a fourth strategy, **measured**, on every circuit with a
2026 session, and it is also how the physics is validated: replay it through the model
and compare the speed trace with the real one. It is inferred, not measured — it
inherits the model's engine — and it is labelled that way everywhere it appears.

## What could not be fitted, and why

The brief asked for vehicle parameters to be fitted rather than assumed. Three could not
be, and saying so is more useful than producing a number that looks fitted:

**ICE power and driveline efficiency.** If the cars deployed the full regulatory ceiling,
every speed bin would imply the same ICE power. Instead the implied value runs from 102 kW
to 457 kW, because observed total power stays flat near 460 kW while the electrical
ceiling falls from 350 kW to 150 kW. The cars are deploying well below the ceiling at
mid-speed — which is the energy management this project exists to model, and cannot also
be assumed away in order to fit the power split. The cars also never run above the
taper's zero point (one sample in 2.4 million), so there is no window where the engine
is alone. Published figures are used and labelled. What the data does give is a floor:
the smallest engine at which each measured lap's energy budget closes has a median of
about 410 kW across the eleven circuits, which is the first evidence behind the
published 400 kW. It also gives a tension the model does not resolve — under that engine
every reference lap ends with 2–3.5 MJ unused, which no qualifying lap does. The power
peaks say the engine cannot be weaker; the lap budgets say its average is. A torque
curve would reconcile them, and the public data does not carry one.

**The straight-line drag state.** The 2026 car has active aero, and the switch is not in
the public data. Its effect is: at 340–350 km/h the cars sit at terminal speed, and even
deploying every watt the taper allows, the drag area can be at most 0.906 m² — the
0.968 m² fitted on coasting is impossible there. Lifting the throttle leaves the low-drag
state, so a coast-down fit measures the other car. The model carries both: the coast
value off throttle and in corners, and the terminal-speed bound under power on a
straight. The true straight-line value lies between 0.76 and 0.91 m²; the bound is the
least drag reduction the data forces.

**Track grip.** A single grip envelope fitted across every session is right on average
and wrong by up to 25% at individual circuits — surface, compound, temperature, and the
quality of the GPS geometry all differ, and a point-mass model on a pooled racing line
sees none of it. One grip factor per 2026 circuit is fitted so the replayed reference
lap matches its measured time (1.00 at Budapest to 1.27 at Shanghai; the outliers are
the circuits with known geometry problems). That is one number fitted to one number; the
shape of the speed trace is left free and is what the accuracy table measures.

**Rolling resistance.** Rolling resistance, engine braking and off-throttle MGU-K regen
are all approximately constant forces. Nothing in their speed dependence separates them,
so only their sum (1197 N) is measurable. Crr is assigned a literature value; the
remainder is carried as an off-throttle term applied only when the car is not under power.

**Regen efficiency.** With no energy channels, nothing distinguishes energy recovered to
the battery from energy lost to the friction brakes.

## How it works

```
Real telemetry  →  Vehicle model  →  DP optimiser  →  Learned policy  →  App
   FastF1           fitted aero       optimal          generalises      animated
   speed, GPS,      + energy          deployment       to unseen        lap + SoC
   throttle         model             per circuit      circuits         trace
```

### 1. Data

Telemetry comes from [FastF1](https://github.com/theOehrly/Fast-F1). Circuit geometry is
built from the GPS traces of clean qualifying laps, resampled onto a 5 m grid.

Two problems had to be solved to make that geometry trustworthy:

*Position samples arrive at ~3.8 Hz*, about 20 m apart at racing speed, which cannot
resolve a 10–50 m radius corner. Samples from every clean lap in the session are pooled,
which densifies the sampling by an order of magnitude.

*Pooling requires knowing where each sample belongs*, and the obvious index —
`RelativeDistance` — is derived from a distance that FastF1 integrates from speed, and
that integration drifts differently on every lap. At the Red Bull Ring laps disagreed by
~80 m, and the traced path came out **64% too long**. Samples are now aligned
geometrically by projection onto a seed path, which removes the dependence on speed
integration. Traced lap lengths land ~1% under official track lengths across all 21
circuits — the correct sign, since a racing line cuts inside the centreline.

### 2. Physics

A longitudinal point-mass model with a friction ellipse:

```
F_traction = min(η·P_available / v, tyre limit)
F_drag     = ½ · ρ · Cd·A · v²        two Cd·A states: straight-line under power, high-drag otherwise
F_roll     = Crr · m · g
m · dv/dt  = F_traction − F_drag − F_roll − F_gradient
```

One transition function integrates this for everything: the optimiser, the baselines,
the validation and the learned-policy scorer (`physics/step.py`). There used to be two,
and they disagreed on clipping — the baseline simulator fixed the speed from the
*requested* deployment and only afterwards noticed the store was empty, which is why
greedy once looked faster than the optimum. Electrical energy is billed ICE-first, so a
traction-limited corner exit is not charged for power the wheels could not use, and
nothing is billed on the braking share of a step.

Aerodynamic and grip coefficients are fitted by regression against real telemetry. The
fits only work because samples are filtered to **straight-line running** using curvature
at each sample's position: most coasting in a session happens in corners, where the car
sheds speed to tyre scrub rather than drag, and including those samples returned
Crr = 0.22, roughly 20× physical.

Cornering and braking limits rise with speed, because downforce does. Without a
tyre-saturation ceiling the model is unbounded — above a critical radius the downforce
term wins and cornering speed goes to infinity, which made the first simulation 13 s/lap
too fast and let Monaco reach 329 km/h.

### 3. Optimisation

Dynamic programming over the lap. Stage is distance; **state is (state of charge, speed)**;
control is a signed fraction of the ERS-K ceiling, positive to deploy and negative to
harvest; cost is elapsed time.

Speed has to be a state. Treating it as determined by forward simulation only holds if
deployment is fixed, and trading energy between parts of the lap is the entire problem.
Two things keep it tractable: the speed ceiling is deployment-independent, so it is
computed once; and each lap is rotated to start at its slowest point, where the ceiling
binds regardless of strategy, so speed periodicity holds by construction.

The per-lap harvest cap is a cumulative constraint that would need a third state
dimension. It is enforced by a Lagrange multiplier on harvested energy, searched until the
lap is periodic.

**What the optimiser discovered rather than being told:** the taper enters the model only
as a ceiling on available power, yet 33.2% of the lap is spent above 290 km/h while only
21.4% of deployed energy goes there — a ratio of 0.65 against 1.00 for speed-blind
deployment. Deployment blocks begin at a median 152 km/h (corner exits); harvest blocks
begin at 237 km/h (the end of straights, where deployment was being throttled away
anyway). That is super clipping, derived rather than encoded.

**One hypothesis that did not survive.** The gain looks strongly related to how much time
a circuit spends above the taper threshold (r = +0.559, p = 0.009) — but lap length
explains it (r = +0.844), and once normalised the relationship vanishes (r = −0.117,
p = 0.61). Gain per kilometre is flat at 0.39–0.55 s/km across the calendar.

### 4. Why this isn't ordinary supervised learning

There is no public dataset of optimal energy deployment, and as noted above the telemetry
contains no energy channels to infer one from. So the pipeline generates its own ground
truth: the DP is solved across 21 circuits at 5 starting states of charge, producing
106,920 (state → optimal control) pairs, and a gradient boosting model learns to reproduce
that policy from local features.

This is **behavioural cloning of a physics-based planner**. Its value is speed: the DP
takes seconds to minutes per circuit, the learned policy evaluates in milliseconds.

Validation is **leave-one-circuit-out**. A random split would leak severely, because
consecutive points on a lap are nearly identical.

**The metric is closed-loop lap time, not regression error.** Each model drives a lap
through the same physics the DP used, and is scored on the percentage of the optimiser's
gain it retains.

The honest result is **68%**, not the 84% the headline average suggests. Every fold that
appears to beat the optimiser is a lap that ended with less charge than it started, which
is not comparable — and only 10 of 21 came back repeatable. The DP receives periodicity as
a hard terminal constraint; a cloned policy only ever sees state-action pairs and does not
rediscover it. **The model is not a replacement for the solver.**

Contrary to expectation, headroom-to-taper is *not* a dominant feature — it ranks 18th at
3.0% importance. State of charge dominates at 18.5%.

## What this is not

- **Not a prediction of what F1 teams actually do.** Teams have factory simulators,
  proprietary tyre and thermal models, and data this project cannot access.
- **The energy model is reconstructed, not measured.** If the assumptions are wrong, the
  optimum shifts.
- **Single-car qualifying lap only.** No traffic, no tyre degradation, no fuel burn, no
  Manual Override Mode, no race-length management.
- **Generic 2026-spec vehicle parameters**, not any specific team's car.
- **Two circuits are missing.** Madrid is a new venue and the 2026 Bahrain Grand Prix runs
  at Sepang, which last hosted F1 in 2017 — before FastF1's coverage begins. Neither has
  telemetry in any year, so neither is included. Ten further circuits had not yet run in
  2026 when this was built and take **geometry only** from an earlier season at the same
  venue; their speed traces are never used and the physics is 2026-spec throughout.
- **Quasi-steady-state.** No transient tyre or aero behaviour, and the active-aero
  state is inferred from its effect rather than observed. Monaco's tunnel has no GPS,
  so its geometry there is wrong and the model is 11 km/h slow through it.

## Stack

Python 3.11 · FastF1 · NumPy / SciPy · LightGBM · FastAPI · Next.js 16 · TypeScript · WebGL

## Live data

Standings, results, qualifying and the calendar come from
[Jolpica-F1](https://api.jolpi.ca/), the maintained successor to the Ergast API, fetched by
server components at request time and cached by Next's Data Cache: completed rounds are
immutable and cache for a week, the current round and season-wide tables refresh hourly.
Pages carry `revalidate = 3600`, so a result is on the site within the hour with no
deploy. The fetcher (`web/lib/f1/jolpica.ts`) queues calls through a small limiter and
sends a descriptive `User-Agent`, both of which Jolpica requires; set `F1_USER_AGENT` to
override the default. Every transform from API rows to what the page shows is a pure
function in `web/lib/f1/standings.ts`, tested against captured responses:

```bash
uv run python -m scripts.capture_fixtures   # refresh web/lib/f1/__fixtures__/
```

Driver portraits and team logos are freely licensed images from Wikimedia Commons,
fetched with attribution and committed under `web/public/media/`:

```bash
uv run python -m scripts.fetch_media        # --force to refetch, --ids norris mclaren
```

Anyone without a usable image is shown as initials on the team colour; `/credits` lists
every image's licence and author. Team colours are transcribed from the broadcast values
in `web/lib/teams.ts`, with a darkened variant for text on the light theme.

## Running locally

Requires Python 3.11+ and Node 20.9+.

```bash
# Frontend — the energy pages read a committed snapshot, the rest fetches Jolpica live
cd web && npm install && npm run dev
```

The energy feature is static. Every API endpoint here is a pure reader, so the service
is snapshotted to `web/public/api/` by `scripts/export_static.py` and the deployed build
needs no Python at all. To run against the live FastAPI instead — worth doing when
changing the API itself — start it and point the frontend at it:

```bash
uv sync
uv run uvicorn api.main:app --reload
# then, in web/.env.local
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

Telemetry is cached to disk on first run — expect the initial build to take a while.
Precomputed geometry and strategies are committed under `data/processed/`, so the
application runs without re-solving the optimiser.

To rebuild the pipeline end to end:

```bash
uv run python -m scripts.build_circuits      # geometry        (~15 min)
uv run python -m scripts.fit_vehicle         # vehicle fit
uv run python -m scripts.simulate_reference  # validation, grip factors, the drivers' laps
uv run python -m scripts.run_optimiser       # DP, all circuits (~25 min)
uv run python -m scripts.build_training_data # DP training set  (~20 min)
uv run python -m scripts.train_policy        # leave-one-circuit-out
uv run python -m scripts.report_results      # refresh this README's tables
uv run python -m scripts.export_static       # refresh the frontend's data snapshot
```

## Deploying

On Vercel, import the repository and set **Root Directory to `web`** — that is the only
setting a monorepo like this needs. The energy pages prerender at build; the live pages
are ISR and regenerate hourly from Jolpica. A build makes around forty Jolpica calls
against a limit of 500 an hour, so it is fine to deploy often but not every few minutes.
No environment variables are required (`F1_USER_AGENT` is optional).

Re-run `scripts.export_static` and commit `web/public/api/` whenever the optimiser output
changes; the build has no Python available to regenerate it.

Tests:

```bash
uv run pytest          # 64 tests — physics, optimiser constraints, API contracts
cd web && npm test     # 44 tests — standings transforms on real API captures, animation timing
```

## Repository layout

```
config/       Regulation constants and vehicle parameters, with sources
data/         Telemetry ingestion, caching, circuit geometry extraction
physics/      Vehicle dynamics and lap simulation
energy/       Battery model, deployment taper, harvest
optimiser/    Dynamic programming solver and baseline strategies
ml/           Feature engineering and the learned policy
api/          FastAPI service exposing precomputed strategies
web/          Next.js site — standings, profiles, and the energy pages
web/lib/f1/   Jolpica fetcher, pure standings transforms, captured fixtures
scripts/      Pipeline entry points, fixture capture, media fetch
tests/        Physics unit tests and optimiser constraint checks
```

## Roadmap

- An engine torque curve, to reconcile the power peaks with the lap energy budgets
- Active aero as a decision variable rather than a state inferred from its effect
- Race-length energy management across a full stint, with Manual Override Mode and
  the 0.5 MJ overtaking allocation — a race feature, so not offered as a qualifying
  strategy here
- A reinforcement learning policy benchmarked against the DP baseline
- DAgger or a periodicity-aware loss, to close the gap the cloned policy leaves

## Author

Built by Akein Tsung, Bachelor of Artificial Intelligence at the University of Technology
Sydney.

The 2026 regulations turned energy deployment into a genuinely interesting constrained
optimisation problem, and this was too good an excuse to write a physics model to pass up.
