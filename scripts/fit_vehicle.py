"""Fit vehicle parameters from 2026 telemetry. Nothing here is tuned by hand.

Fit order matters, because the quantities are not simultaneously identifiable.

Every fit runs on STRAIGHT-LINE samples, selected by lateral acceleration computed from
track curvature at each sample's position. This filter is what makes the whole thing
work. Most coasting in a session happens in corners, where the car sheds speed to tyre
scrub rather than drag; including those samples attributes cornering losses to Cd*A and
returned Crr = 0.22, some 20x physical.

1. DRAG, on straight-line coasting (throttle off, brake off).
   The brief suggests fitting drag on coast-down *and* full-throttle acceleration, but
   the full-throttle half is circular: at full throttle the propulsive term is
   P_ice + P_electric, and P_electric is exactly the unobservable quantity this project
   exists to reconstruct. Coasting is the only regime where propulsive power is known.

       m * dv/dt = -(1/2) rho Cd A v^2  -  F_offthrottle

   Two terms, not three. Off-throttle the MGU-K recovers at roughly constant torque,
   which is a constant FORCE; an earlier constant-POWER term (P/v) fought the constant
   term and wrecked the fit. Rolling resistance, engine braking and regen are all
   constant forces, so this data cannot separate them — only their sum is measured, and
   Crr is therefore assumed rather than fitted. That is stated in the output.

2. GRIP, from the envelope of lateral acceleration against speed. At the limit
   a_lat = mu*(g + rho*Cl*A*v^2 / 2m), which is linear in v^2, so the intercept gives
   mu*g and the slope gives Cl*A. Only cornering samples carry information here.

3. POWER, from full-throttle data once drag is known. Inverting the force balance gives
   observed propulsive power, and since P_obs = eta*(P_ice + P_elec(v)) with P_elec known
   exactly from the taper, regressing P_obs on P_elec(v) yields eta as the slope and
   eta*P_ice as the intercept.

   ASSUMPTIONS: this treats a qualifying flying lap as deploying the full regulatory
   ceiling, which is approximately what a quali lap does but is not a measurement. It
   also has weak leverage: below 290 km/h the electrical ceiling is a flat 350 kW, so
   P_ice and eta only separate using the few percent of samples inside the taper band.

Run:  uv run python -m scripts.fit_vehicle
"""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

from config.regulations import ERSK_MAX_POWER_W, max_deploy_power_w
from config.vehicle import GRAVITY_M_S2, LAP_MASS_KG, air_density
from data.cache import PROCESSED_DIR, enable
from data.dynamics import load as load_dynamics
from data.dynamics import load_reference_traces

COAST_THROTTLE_MAX = 3.0
FULL_THROTTLE_MIN = 98.0
MIN_SPEED_MPS = 15.0
# Lateral acceleration below which a sample counts as straight-line running [m/s^2].
# ~0.2 g, well under the ~5 g these cars sustain, so cornering losses are negligible.
MAX_LATERAL_FOR_STRAIGHT = 2.0
# Rolling resistance is not identifiable from this data: it is a constant force, and so
# are engine braking and off-throttle regen, so nothing in the speed dependence separates
# them. Assigned a literature value for a slick racing tyre and flagged as an assumption.
ASSUMED_CRR = 0.012
# Above this speed an F1 car is power-limited rather than traction- or torque-limited,
# so observed propulsive power measures what the power unit delivers. ~234 km/h.
POWER_LIMITED_MIN_MPS = 65.0
# Only laps within this multiple of the session best count as flying laps. A qualifying
# session is mostly out-laps and in-laps, driven far below the limit and with entirely
# different energy management.
FLYING_LAP_MAX_RATIO = 1.05
# Quantile defining the grip envelope. Most cornering is submaximal so a mean would
# understate the limit, but p98 tracks residual alignment outliers rather than the car.
GRIP_ENVELOPE_Q = 0.90
# Speed above which the measured lateral-acceleration envelope stops rising [m/s].
GRIP_SATURATION_MPS = 55.0

# Used when the telemetry cannot identify the power split (see fit_power). Published
# 2026 figures, not measurements:
#   https://www.formula1.com/en/latest/article/2026-regulations-explained-all-you-need-
#   to-know-about-f1s-new-power-units.14jfv7a36905uDJDdNyfQd
ASSUMED_P_ICE_W = 400_000.0
ASSUMED_DRIVELINE_EFFICIENCY = 0.95
# Fraction of mechanical braking energy that reaches the CU-K bus. Not measurable here:
# the telemetry has no energy channels, so nothing distinguishes energy sent to the
# battery from energy lost to the friction brakes.
ASSUMED_REGEN_EFFICIENCY = 0.90


@dataclass
class FitReport:
    cd_a: float
    crr: float
    f_offthrottle_n: float
    cd_a_ci: tuple[float, float]
    coast_n: int
    coast_condition_number: float
    coast_r2: float
    cl_a: float
    mu_lat: float
    a_lat_ceiling: float
    grip_n: int
    grip_r2: float
    mu_brake: float
    brake_n: int
    regen_efficiency: float
    p_ice_w: float
    driveline_efficiency: float
    power_n: int
    power_r2: float
    power_source: str
    power_identifiable: bool
    implied_p_ice_by_bin_w: list[float]
    p_total_observed_max_w: float
    air_density: float
    mass_kg: float
    sessions: list[str]
    assumptions: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cd_a_ci"] = list(self.cd_a_ci)
        return d


def coasting_samples(df: pd.DataFrame) -> pd.DataFrame:
    """Straight-line coasting only.

    The lateral-acceleration filter is what makes this fit work. Most coasting in a
    session happens in corners, where the car is shedding speed to tyre scrub rather
    than to drag; leaving those samples in attributes cornering losses to Cd*A and Crr
    and produces nonsense (a first attempt returned Crr = 0.33, ~30x physical).
    """
    # Deliberately NOT filtered on accel < 0. Coasting always decelerates physically, but
    # dv/dt carries ~2.2 m/s^2 of noise from 1 km/h speed quantisation at ~4 Hz, which is
    # the same order as the deceleration itself at low speed. Dropping the positive tail
    # would truncate a symmetric error distribution and bias the fit.
    return df[
        (df["throttle"] <= COAST_THROTTLE_MAX)
        & (~df["brake"])
        & (df["a_lat"].notna())
        & (df["a_lat"] < MAX_LATERAL_FOR_STRAIGHT)
        & (df["v"] > MIN_SPEED_MPS)
    ]


def fit_drag(df: pd.DataFrame, mass: float, rho: float) -> dict:
    """Fit coasting resistance as  F = 0.5*rho*Cd*A*v^2 + F_offthrottle.

    Two terms, not three. A first attempt used [v^2, 1, 1/v], reading the 1/v term as
    constant-power MGU-K regen, and returned Crr = 0.22 — roughly 20x physical. The data
    is unambiguous about why: coast resistance extrapolates to ~1.2 kN at zero speed,
    far beyond rolling resistance (~91 N), and that constant offset has to go somewhere.

    Off-throttle the MGU-K recovers at approximately constant torque, which is a constant
    FORCE, not constant power. So the correct decomposition is drag plus a single
    speed-independent term covering rolling resistance, engine braking and regen
    together. Those three cannot be separated by this data — nothing distinguishes them
    by speed dependence — so no attempt is made to pretend otherwise. Crr is assigned an
    assumed literature value and the remainder is attributed to off-throttle braking.
    """
    coast = coasting_samples(df)
    if len(coast) < 500:
        raise ValueError(f"only {len(coast)} straight-line coasting samples; too few")

    v = coast["v"].to_numpy().astype(float)
    y = -coast["accel"].to_numpy().astype(float) * mass  # total resistive force [N]
    X = np.column_stack([0.5 * rho * v**2, np.ones_like(v)])

    scale = np.linalg.norm(X, axis=0)
    Xn = X / scale
    beta_n, *_ = np.linalg.lstsq(Xn, y, rcond=None)
    resid = y - Xn @ beta_n
    keep = np.abs(resid) < 3.0 * resid.std()
    beta_n, *_ = np.linalg.lstsq(Xn[keep], y[keep], rcond=None)
    beta = beta_n / scale

    resid = y[keep] - Xn[keep] @ beta_n
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y[keep] - y[keep].mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    dof = max(1, int(keep.sum()) - 2)
    cov_n = ss_res / dof * np.linalg.pinv(Xn[keep].T @ Xn[keep])
    se = np.sqrt(np.maximum(np.diag(cov_n), 0.0)) / scale

    cd_a = float(beta[0])
    f_const = float(beta[1])
    f_rolling = ASSUMED_CRR * mass * GRAVITY_M_S2

    return {
        "cd_a": cd_a,
        "crr": ASSUMED_CRR,
        "f_offthrottle_n": max(0.0, f_const - f_rolling),
        "f_const_n": f_const,
        "cd_a_ci": (float(beta[0] - 1.96 * se[0]), float(beta[0] + 1.96 * se[0])),
        "f_const_se": float(se[1]),
        "coast_n": int(keep.sum()),
        "coast_v_range_kph": (float(v.min() * 3.6), float(v.max() * 3.6)),
        "coast_condition_number": float(np.linalg.cond(Xn[keep])),
        "coast_r2": float(r2),
    }


def fit_grip(df: pd.DataFrame, mass: float, rho: float) -> dict:
    """Fit Cl*A and mu_lat from the envelope of lateral acceleration against speed.

    At the limit  a_lat = mu*(g + rho*Cl*A*v^2 / 2m), which is linear in v^2. Regressing
    the peak observed a_lat in each speed bin gives mu*g as the intercept and Cl*A from
    the slope. Only cornering samples count: on a straight a_lat is near zero and says
    nothing about available grip.
    """
    corner = df[
        df["a_lat"].notna()
        & (np.abs(df["curvature"]) > 1.0 / 400.0)
        & (df["v"] > MIN_SPEED_MPS)
    ]
    if len(corner) < 1000:
        return {"mu_lat": float("nan"), "cl_a": float("nan"), "grip_n": 0,
                "grip_r2": float("nan")}

    work = corner[["v", "a_lat"]].copy()
    work["bin"] = pd.cut(work["v"], bins=25)
    env = (
        work.groupby("bin", observed=True)
        .agg(v=("v", "median"), a_lat=("a_lat", lambda s: s.quantile(GRIP_ENVELOPE_Q)),
             n=("v", "size"))
        .dropna()
    )
    # Thinly populated bins at the top of the speed range are dominated by residual
    # position-alignment error and show physically impossible values (>10 g), so they are
    # excluded rather than allowed to set the ceiling.
    env = env[env["n"] >= 5000]
    if len(env) < 5:
        return {"mu_lat": float("nan"), "cl_a": float("nan"), "grip_n": int(len(env)),
                "grip_r2": float("nan"), "a_lat_ceiling": float("nan")}

    # Fit the rising part below saturation, then read the ceiling off the plateau.
    rising = env[env["v"] < GRIP_SATURATION_MPS]
    plateau = env[env["v"] >= GRIP_SATURATION_MPS]
    if len(rising) < 4 or len(plateau) < 2:
        rising, plateau = env, env

    res = stats.linregress(rising["v"].to_numpy() ** 2, rising["a_lat"].to_numpy())
    mu_lat = float(res.intercept / GRAVITY_M_S2)
    cl_a = float(2.0 * mass * res.slope / (mu_lat * rho)) if mu_lat > 0 else float("nan")
    return {
        "mu_lat": mu_lat,
        "cl_a": cl_a,
        "a_lat_ceiling": float(np.median(plateau["a_lat"].to_numpy())),
        "grip_n": int(len(env)),
        "grip_r2": float(res.rvalue**2),
    }


def fit_braking(df: pd.DataFrame, mass: float, rho: float, cd_a: float,
                cl_a: float) -> dict:
    """mu_brake from straight-line braking, once aero drag is removed.

    Restricted to low lateral acceleration: a car braking while turning is sharing its
    grip between the two axes and cannot be at the longitudinal limit.
    """
    brk = df[
        df["brake"]
        & (df["v"] > MIN_SPEED_MPS)
        & (df["accel"] < 0)
        & df["a_lat"].notna()
        & (df["a_lat"] < MAX_LATERAL_FOR_STRAIGHT)
    ]
    if len(brk) < 500:
        return {"mu_brake": float("nan"), "brake_n": 0, "brake_peak_decel": float("nan")}

    v = brk["v"].to_numpy().astype(float)
    decel = -brk["accel"].to_numpy().astype(float)
    tyre_a = decel - (0.5 * rho * cd_a * v**2) / mass
    normal_a = GRAVITY_M_S2 + (0.5 * rho * cl_a * v**2) / mass

    # The limit is the upper envelope, not the mean: most braking is submaximal, so an
    # average would understate what the car can do.
    ratio = tyre_a / normal_a
    return {
        "mu_brake": float(np.quantile(ratio, 0.98)),
        "brake_n": int(len(brk)),
        "brake_peak_decel": float(np.quantile(decel, 0.99)),
    }


def fit_power(df: pd.DataFrame, mass: float, rho: float, cd_a: float, crr: float) -> dict:
    """Invert full-throttle dynamics for propulsive power, then split ICE from electric.

    IDENTIFIABILITY WARNING. Below 290 km/h the regulatory electrical ceiling is a flat
    350 kW, so P_obs = eta*(P_ice + 350kW) is a single number and P_ice cannot be
    separated from eta at all. The only leverage comes from samples inside the taper
    band, where P_elec falls with speed — and the cars spend only a few percent of the
    lap there. The number of bins carrying that leverage is reported so the separation
    can be judged rather than trusted.
    """
    # Only high speed, and no accel filter. Two separate reasons:
    #
    # Below ~230 km/h the car is traction- and torque-limited, not power-limited, so
    # P_obs there measures what the tyres and gearing allow, not what the power unit can
    # deliver. Mixing those bins with power-limited ones inverted the regression: at the
    # top of the range P_obs is large (drag scales as v^3) exactly where P_elec is small,
    # which drove the slope negative and returned P_ice = 846 kW.
    #
    # And requiring accel > 0 would truncate noise: near terminal velocity the true
    # acceleration is ~0, so keeping only positive samples keeps only upward noise.
    full = df[
        (df["throttle"] >= FULL_THROTTLE_MIN)
        & (~df["brake"])
        & (df["v"] >= POWER_LIMITED_MIN_MPS)
        & df["a_lat"].notna()
        & (df["a_lat"] < MAX_LATERAL_FOR_STRAIGHT)
        & df["is_clean"]
        & (df["lap_time_ratio"] < FLYING_LAP_MAX_RATIO)
    ]
    empty = {
        "p_ice_w": float("nan"), "driveline_efficiency": float("nan"),
        "power_n": int(len(full)), "power_r2": float("nan"),
        "p_total_max_w": float("nan"), "taper_bins": 0, "eta_se": float("nan"),
    }
    if len(full) < 500:
        return empty

    v = full["v"].to_numpy().astype(float)
    a = full["accel"].to_numpy().astype(float)
    resist = 0.5 * rho * cd_a * v**2 + crr * mass * GRAVITY_M_S2
    p_obs = (mass * a + resist) * v
    p_elec = np.array([max_deploy_power_w(vi * 3.6, "normal") for vi in v])

    # MEAN per speed bin, not an upper quantile. Above the traction-limited region every
    # full-throttle sample is by definition using all available power, so the bin mean is
    # the right estimator and the ~137 kW of per-sample noise averages out. A high
    # quantile would instead track the noise ceiling and inflate the result.
    frame = pd.DataFrame({"v": v, "p_obs": p_obs, "p_elec": p_elec})
    frame["bin"] = pd.cut(frame["v"], bins=25)
    env = (
        frame.groupby("bin", observed=True)
        .agg(v=("v", "median"), p_elec=("p_elec", "median"),
             p_obs=("p_obs", "mean"), n=("v", "size"))
        .dropna()
    )
    env = env[(env["p_obs"] > 0) & (env["n"] >= 200)]
    if len(env) < 5:
        return empty

    taper_bins = int((env["p_elec"] < ERSK_MAX_POWER_W - 1.0).sum())
    res = stats.linregress(env["p_elec"].to_numpy(), env["p_obs"].to_numpy())

    # Diagnostic: what ICE power would each speed bin imply, if the car really were
    # deploying the full ceiling there? A constant ICE must give a constant answer.
    implied = env["p_obs"] / ASSUMED_DRIVELINE_EFFICIENCY - env["p_elec"]
    implied_spread_w = float(implied.max() - implied.min())
    identifiable = implied_spread_w < 100_000.0

    out = {
        "p_total_observed_max_w": float(env["p_obs"].max()),
        "power_n": int(len(full)),
        "power_r2": float(res.rvalue**2),
        "eta_slope_raw": float(res.slope),
        "eta_se": float(res.stderr),
        "taper_bins": taper_bins,
        "implied_p_ice_by_bin_w": [float(x) for x in implied],
        "implied_p_ice_spread_w": implied_spread_w,
        "power_identifiable": bool(identifiable),
    }

    if identifiable:
        eta = float(np.clip(res.slope, 0.80, 1.0))
        out["driveline_efficiency"] = eta
        out["p_ice_w"] = float(res.intercept / eta)
        out["power_source"] = "fitted"
    else:
        # The full-deployment premise is contradicted by the data, so P_ice and eta are
        # not recoverable from it. Published values are used instead and labelled as
        # assumptions rather than dressed up as measurements.
        out["driveline_efficiency"] = ASSUMED_DRIVELINE_EFFICIENCY
        out["p_ice_w"] = ASSUMED_P_ICE_W
        out["power_source"] = "assumed (not identifiable from telemetry)"
    return out


def main() -> int:
    warnings.filterwarnings("ignore")
    enable()

    df, weather = load_dynamics()
    traces = load_reference_traces()
    used = sorted(df["circuit"].astype(str).unique())
    print(f"Fitting on {len(used)} 2026-native qualifying sessions "
          "(fallback sessions are a different car and are excluded)")
    for c in used:
        print(f"  {c:<18} {int((df['circuit'] == c).sum()):>8,} samples")

    mass = LAP_MASS_KG
    rho_vals = [
        air_density(row["pressure_mbar"], row["air_temp_c"], row["humidity_pct"] or 0.0)
        for _, row in weather.iterrows()
        if pd.notna(row.get("pressure_mbar")) and pd.notna(row.get("air_temp_c"))
    ]
    rho = float(np.median(rho_vals)) if rho_vals else 1.225

    print(f"\nPooled {len(df):,} samples | mass {mass:.0f} kg | "
          f"median session air density {rho:.4f} kg/m^3")

    drag = fit_drag(df, mass, rho)
    grip = fit_grip(df, mass, rho)
    brake = fit_braking(df, mass, rho, drag["cd_a"], grip["cl_a"])
    power = fit_power(df, mass, rho, drag["cd_a"], drag["crr"])

    report = FitReport(
        cd_a=drag["cd_a"],
        crr=drag["crr"],
        f_offthrottle_n=drag["f_offthrottle_n"],
        cd_a_ci=drag["cd_a_ci"],
        coast_n=drag["coast_n"],
        coast_condition_number=drag["coast_condition_number"],
        coast_r2=drag["coast_r2"],
        cl_a=grip["cl_a"],
        mu_lat=grip["mu_lat"],
        a_lat_ceiling=grip["a_lat_ceiling"],
        grip_n=grip["grip_n"],
        grip_r2=grip["grip_r2"],
        mu_brake=brake["mu_brake"],
        brake_n=brake["brake_n"],
        regen_efficiency=ASSUMED_REGEN_EFFICIENCY,
        p_ice_w=power["p_ice_w"],
        driveline_efficiency=power["driveline_efficiency"],
        power_n=power["power_n"],
        power_r2=power["power_r2"],
        power_source=power["power_source"],
        power_identifiable=power["power_identifiable"],
        implied_p_ice_by_bin_w=power["implied_p_ice_by_bin_w"],
        p_total_observed_max_w=power["p_total_observed_max_w"],
        air_density=rho,
        mass_kg=mass,
        sessions=[f"2026 {c} Q" for c in used],
        assumptions=[
            "Drag fitted on coasting only; full-throttle data cannot identify drag "
            "because electrical deployment is unobservable.",
            f"P_ice ({ASSUMED_P_ICE_W / 1000:.0f} kW) and driveline efficiency "
            f"({ASSUMED_DRIVELINE_EFFICIENCY}) are PUBLISHED/ASSUMED values, not fits. "
            "The telemetry cannot identify them: observed total power stays flat while "
            "the electrical ceiling falls, showing the cars do not deploy the full "
            "ceiling, so the P_obs = eta*(P_ice + P_elec) relation does not hold.",
            f"Crr is NOT identifiable from this data and is assumed to be {ASSUMED_CRR}. "
            "Rolling resistance, engine braking and off-throttle regen are all constant "
            "forces, so nothing in the speed dependence separates them; only their sum "
            "is measured.",
            f"Mass {mass:.0f} kg = 768 kg regulatory minimum + 10 kg assumed qualifying "
            "fuel load.",
            f"Regen efficiency ({ASSUMED_REGEN_EFFICIENCY}) is assumed. Public telemetry "
            "has no energy channels, so nothing separates energy recovered to the "
            "battery from energy lost to the friction brakes.",
        ],
    )

    _print_report(report, drag)
    out = PROCESSED_DIR / "vehicle_fit.json"
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"\nWritten: {out}")
    return 0


def _print_report(r: FitReport, drag: dict) -> None:
    print("\n" + "=" * 78)
    print("FITTED VEHICLE PARAMETERS")
    print("=" * 78)
    lo, hi = drag["coast_v_range_kph"]
    print(f"  Cd*A                 {r.cd_a:8.3f} m^2   "
          f"95% CI [{r.cd_a_ci[0]:.3f}, {r.cd_a_ci[1]:.3f}]")
    print(f"  Crr                  {r.crr:8.4f}       ASSUMED (not identifiable)")
    print(f"  F_offthrottle        {r.f_offthrottle_n:8.0f} N     "
          f"+/- {drag['f_const_se']:.0f} N  (engine braking + MGU-K regen)")
    print(f"     {r.coast_n:,} straight-line coasting samples over "
          f"{lo:.0f}-{hi:.0f} km/h")
    print(f"     R^2 {r.coast_r2:.3f}, condition number {r.coast_condition_number:.1f}")
    print(f"  Cl*A                 {r.cl_a:8.3f} m^2")
    print(f"  mu_lat               {r.mu_lat:8.3f}        "
          f"(envelope R^2 {r.grip_r2:.3f}, {r.grip_n} speed bins)")
    print(f"  a_lat ceiling        {r.a_lat_ceiling:8.1f} m/s^2 "
          f"({r.a_lat_ceiling / GRAVITY_M_S2:.1f} g, tyre saturation)")
    print(f"  mu_brake             {r.mu_brake:8.3f}        ({r.brake_n:,} samples)")
    print(f"  P_ice                {r.p_ice_w / 1000:8.1f} kW    {r.power_source}")
    print(f"  driveline efficiency {r.driveline_efficiency:8.3f}      "
          f"({r.power_n:,} flying-lap samples)")
    print(f"  air density          {r.air_density:8.4f} kg/m^3")

    if not r.power_identifiable:
        implied = np.array(r.implied_p_ice_by_bin_w) / 1000
        print("\n  POWER SPLIT NOT IDENTIFIABLE — the data contradicts full deployment.")
        print("  If the car deployed the full regulatory ceiling, every speed bin would")
        print("  imply the same ICE power. Implied P_ice by ascending speed bin (kW):")
        print("    " + "  ".join(f"{x:.0f}" for x in implied))
        print(f"  Spread {implied.max() - implied.min():.0f} kW. Observed total power is "
              f"flat at ~{r.p_total_observed_max_w / 1000:.0f} kW while the electrical")
        print("  ceiling falls from 350 kW to 150 kW, so the cars are deploying well")
        print("  below the ceiling at mid-speed. That is the energy management this")
        print("  project models — it cannot also be assumed away to fit the power split.")

    print("\nPLAUSIBILITY CHECK (published 2026 figures, for orientation only)")
    _check("Cd*A", r.cd_a, 0.9, 1.8, "m^2")
    _check("Crr", r.crr, 0.005, 0.030, "")
    _check("Cl*A", r.cl_a, 2.0, 6.0, "m^2")
    # mu here is an effective coefficient absorbing tyre load sensitivity, so it runs
    # higher than a textbook friction coefficient.
    _check("mu_lat", r.mu_lat, 1.2, 3.0, "")
    _check("mu_brake", r.mu_brake, 1.0, 2.5, "")
    _check("P_ice", r.p_ice_w / 1000, 300.0, 500.0, "kW")

    print("\nASSUMPTIONS")
    for a in r.assumptions:
        print(f"  - {a}")


def _check(name: str, value: float, lo: float, hi: float, unit: str) -> None:
    if not np.isfinite(value):
        print(f"  {name:<10} NOT FITTED")
        return
    ok = lo <= value <= hi
    flag = "ok " if ok else "OUT OF RANGE"
    print(f"  {name:<10} {value:9.3f} {unit:<5} expected {lo}-{hi} {unit:<5} {flag}")


if __name__ == "__main__":
    raise SystemExit(main())
