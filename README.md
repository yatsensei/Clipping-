# Clipping

**Where should a 2026 Formula 1 car deploy its battery around a lap?**

A physics-informed optimiser that computes the lap-time-optimal electrical deployment
strategy for every circuit on the 2026 calendar, built on real telemetry, and an
interactive visualiser that animates the result.

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

The optimiser gains **2.35 s per lap on average** over uniform constant deployment,
ranging from +1.54 s at Monaco to +2.77 s at Spa. Both strategies are held to the same
constraint: the lap must end with at least the energy it started with, or it is not a
strategy, it is a one-off.

<!-- RESULTS:START -->

### Lap time gained, per circuit

Measured against **uniform constant deployment** at the same starting state of charge, both strategies required to end the lap with at least the energy they began with. All times in seconds.

| Circuit | Uniform | Optimal | **Gain** | Greedy | Greedy debt | Optimal clipping | Greedy clipping |
|---|---:|---:|---:|---:|---:|---:|---:|
| spa-francorchamps | 107.710 | 104.938 | **+2.772** | 101.803 | −2.00 MJ | 0% | 61% |
| las-vegas | 95.061 | 92.345 | **+2.716** | 89.087 | −2.00 MJ | 0% | 64% |
| suzuka | 94.604 | 91.927 | **+2.676** | 89.635 | −2.00 MJ | 0% | 50% |
| silverstone | 89.112 | 86.452 | **+2.660** | 84.017 | −2.00 MJ | 0% | 57% |
| miami-gardens | 89.106 | 86.511 | **+2.596** | 84.902 | −2.00 MJ | 0% | 56% |
| yas-marina | 90.172 | 87.599 | **+2.573** | 85.545 | −2.00 MJ | 0% | 54% |
| shanghai | 99.774 | 97.210 | **+2.564** | 95.664 | −2.00 MJ | 0% | 50% |
| lusail | 89.840 | 87.318 | **+2.521** | 85.299 | −2.00 MJ | 0% | 46% |
| baku | 107.323 | 104.911 | **+2.411** | 101.924 | −2.00 MJ | 0% | 56% |
| marina-bay | 91.739 | 89.330 | **+2.409** | 87.383 | −2.00 MJ | 0% | 47% |
| montreal | 74.348 | 71.978 | **+2.370** | 69.696 | −2.00 MJ | 0% | 58% |
| monza | 83.198 | 80.846 | **+2.352** | 76.884 | −2.00 MJ | 0% | 62% |
| spielberg | 68.741 | 66.399 | **+2.342** | 64.369 | −2.00 MJ | 0% | 47% |
| austin | 97.539 | 95.235 | **+2.304** | 93.512 | −2.00 MJ | 0% | 47% |
| melbourne | 83.440 | 81.147 | **+2.293** | 78.197 | −2.00 MJ | 0% | 55% |
| sao-paulo | 71.430 | 69.274 | **+2.156** | 67.638 | −2.00 MJ | 0% | 47% |
| mexico-city | 75.092 | 72.979 | **+2.113** | 71.708 | −2.00 MJ | 0% | 38% |
| barcelona | 76.757 | 74.755 | **+2.001** | 73.079 | −2.00 MJ | 0% | 43% |
| zandvoort | 77.253 | 75.286 | **+1.967** | 74.010 | −2.00 MJ | 0% | 45% |
| budapest | 77.338 | 75.433 | **+1.905** | 74.389 | −2.00 MJ | 0% | 38% |
| monte-carlo | 73.646 | 72.111 | **+1.536** | 71.835 | −2.00 MJ | 0% | 33% |
| **mean** | | | **+2.345** | | −2.00 MJ | 0% | 50% |

Greedy is faster on every circuit and repeatable on none of them: it ends each lap around 2 MJ in debt, having spent energy it never repays. That is why it is not the baseline.

### Learned policy — leave-one-circuit-out

| Held-out circuit | DP gain | Model gain | Retained | Repeatable |
|---|---:|---:|---:|:--:|
| baku | +2.411 s | +3.196 s | 133% | **no** |
| spa-francorchamps | +2.772 s | +3.056 s | 110% | **no** |
| spielberg | +2.342 s | +2.561 s | 109% | **no** |
| montreal | +2.370 s | +2.548 s | 108% | **no** |
| melbourne | +2.293 s | +2.319 s | 101% | **no** |
| silverstone | +2.660 s | +2.671 s | 100% | **no** |
| monza | +2.352 s | +2.275 s | 97% | **no** |
| yas-marina | +2.573 s | +2.361 s | 92% | yes |
| suzuka | +2.676 s | +2.390 s | 89% | yes |
| sao-paulo | +2.156 s | +1.879 s | 87% | **no** |
| miami-gardens | +2.596 s | +2.251 s | 87% | **no** |
| mexico-city | +2.113 s | +1.820 s | 86% | yes |
| barcelona | +2.001 s | +1.668 s | 83% | yes |
| marina-bay | +2.409 s | +1.922 s | 80% | **no** |
| austin | +2.304 s | +1.821 s | 79% | yes |
| las-vegas | +2.716 s | +1.973 s | 73% | **no** |
| zandvoort | +1.967 s | +1.387 s | 71% | yes |
| shanghai | +2.564 s | +1.704 s | 66% | yes |
| lusail | +2.521 s | +1.633 s | 65% | yes |
| monte-carlo | +1.536 s | +0.447 s | 29% | yes |
| budapest | +1.905 s | +0.449 s | 24% | yes |

Mean across all 21 folds: **84%**. On the 10 folds that produced a repeatable lap: **68%** (median 75%, best 92%).

Scores above 100% are not the model beating the optimiser. The DP is optimal subject to periodicity, and the only way past it is to break that constraint — every fold above 100% ends the lap with less charge than it started.

| Model | All folds | Repeatable laps only | Repeatable | Mean MAE |
|---|---:|---:|---:|---:|
| `gbm` | 84% | 68% | 10/21 | 0.14 |
| `gbm_reg` | 67% | 41% | 5/21 | 0.20 |
| `linear` | -72% | -148% | 3/21 | 0.33 |
| `always-deploy` | -73% | — | 0/21 | 0.93 |

### Physics model accuracy

Forward simulation against the measured qualifying lap, on the circuits with 2026 telemetry.

| Circuit | Speed RMSE | Simulated lap | Measured lap | Error |
|---|---:|---:|---:|---:|
| barcelona | 21.9 km/h | 73.08 s | 74.68 s | -1.60 s |
| budapest | 16.1 km/h | 74.39 s | 77.22 s | -2.83 s |
| melbourne | 26.6 km/h | 78.20 s | 78.52 s | -0.32 s |
| miami-gardens | 22.8 km/h | 84.90 s | 87.80 s | -2.90 s |
| monte-carlo | 29.4 km/h | 71.84 s | 72.09 s | -0.26 s |
| montreal | 22.4 km/h | 69.70 s | 72.65 s | -2.95 s |
| shanghai | 24.7 km/h | 95.66 s | 92.06 s | +3.60 s |
| silverstone | 25.6 km/h | 84.02 s | 88.39 s | -4.37 s |
| spa-francorchamps | 29.9 km/h | 101.80 s | 104.89 s | -3.09 s |
| spielberg | 24.4 km/h | 64.37 s | 66.41 s | -2.04 s |
| suzuka | 30.5 km/h | 89.64 s | 89.08 s | +0.56 s |
| **mean** | **24.9 km/h** | | | **2.23 s abs** |

### Fitted vehicle parameters

| Parameter | Value | Basis |
|---|---:|---|
| Cd·A | 0.968 m² | fitted — 95% CI [0.954, 0.981], 29,275 straight-line coasting samples |
| Cl·A | 5.586 m² | fitted — lateral-acceleration envelope |
| μ lateral | 1.753 | fitted |
| μ braking | 1.386 | fitted |
| Lateral ceiling | 44.4 m/s² | fitted — tyre saturation, 4.5 g |
| Off-throttle force | 1197 N | fitted — engine braking plus MGU-K regen |
| Crr | 0.012 | **assumed** — not identifiable (see below) |
| ICE power | 400 kW | **assumed** — published figure, not identifiable |
| Driveline efficiency | 0.95 | **assumed** |
| Regen efficiency | 0.90 | **assumed** — no energy channels exist to measure it |
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
| Cd·A, Cl·A, grip coefficients, off-throttle force | **Fitted** to measured telemetry |
| ICE power, driveline and regen efficiency, Crr | **Assumed.** Not identifiable — see below |
| Deployment, state of charge, harvest, clipping | **Model output.** Nothing here is measured |
| Lap times and gains | **Model output** |

Every API response carries a `data_type` field marking which of these it is, and the
interface renders that distinction rather than hiding it.

## What could not be fitted, and why

The brief asked for vehicle parameters to be fitted rather than assumed. Three could not
be, and saying so is more useful than producing a number that looks fitted:

**ICE power and driveline efficiency.** If the cars deployed the full regulatory ceiling,
every speed bin would imply the same ICE power. Instead the implied value runs from 102 kW
to 457 kW, because observed total power stays flat near 460 kW while the electrical
ceiling falls from 350 kW to 150 kW. The cars are deploying well below the ceiling at
mid-speed — which is the energy management this project exists to model, and cannot also
be assumed away in order to fit the power split. Published figures are used and labelled.

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
F_drag     = ½ · ρ · Cd·A · v²
F_roll     = Crr · m · g
m · dv/dt  = F_traction − F_drag − F_roll − F_gradient
```

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
- **Quasi-steady-state.** No transient tyre or aero behaviour. Monaco's simulated top
  speed is 318 km/h against a measured 286, though its lap time matches to 0.26 s.

## Stack

Python 3.11 · FastF1 · NumPy / SciPy · LightGBM · FastAPI · Next.js 16 · TypeScript · WebGL

## Running locally

Requires Python 3.11+ and Node 20.9+.

```bash
# Backend
uv sync
uv run python -m scripts.build_circuits    # downloads and caches telemetry on first run
uv run uvicorn api.main:app --reload

# Frontend, in a second terminal
cd web && npm install && npm run dev
```

Telemetry is cached to disk on first run — expect the initial build to take a while.
Precomputed geometry and strategies are committed under `data/processed/`, so the
application runs without re-solving the optimiser.

To rebuild the pipeline end to end:

```bash
uv run python -m scripts.build_circuits      # geometry        (~15 min)
uv run python -m scripts.fit_vehicle         # vehicle fit
uv run python -m scripts.run_optimiser       # DP, all circuits (~25 min)
uv run python -m scripts.build_training_data # DP training set  (~20 min)
uv run python -m scripts.train_policy        # leave-one-circuit-out
uv run python -m scripts.report_results      # refresh this README's tables
```

Tests:

```bash
uv run pytest          # 64 tests — physics, optimiser constraints, API contracts
cd web && npm test     # 21 tests — animation timing, scroll mapping
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
web/          Next.js frontend — landing page and analysis view
scripts/      Pipeline entry points
tests/        Physics unit tests and optimiser constraint checks
```

## Roadmap

- Manual Override Mode and the 0.5 MJ overtaking allocation
- Active aero drag state as a joint optimisation variable
- Race-length energy management across a full stint
- A reinforcement learning policy benchmarked against the DP baseline
- DAgger or a periodicity-aware loss, to close the gap the cloned policy leaves

## Author

Built by Akein Tsung, Bachelor of Artificial Intelligence at the University of Technology
Sydney.

The 2026 regulations turned energy deployment into a genuinely interesting constrained
optimisation problem, and this was too good an excuse to write a physics model to pass up.
