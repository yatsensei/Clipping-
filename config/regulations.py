"""2026 Formula 1 power unit regulation constants.

Every value carries its source. Values are tagged:

    VERIFIED    quoted from the FIA regulations PDF, with article number
    SECONDARY   reported by a reputable outlet, not yet confirmed against an FIA document
    ASSUMPTION  chosen by this project; not a regulatory figure

Anything not tagged VERIFIED must be surfaced as an assumption in the UI.

Primary source
--------------
FIA 2026 Formula 1 Power Unit Technical Regulations, Issue 7, published 11 June 2024.
https://www.fia.com/sites/default/files/fia_2026_formula_1_technical_regulations_pu_-_issue_7_-_2024-06-11_1.pdf
Retrieved and text-extracted 2026-08-08. Article numbers below refer to this issue.
"""

from __future__ import annotations

from typing import Final, Literal

# --------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------

PU_REGS_ISSUE: Final[str] = "Issue 7"
PU_REGS_DATE: Final[str] = "2024-06-11"
PU_REGS_URL: Final[str] = (
    "https://www.fia.com/sites/default/files/"
    "fia_2026_formula_1_technical_regulations_pu_-_issue_7_-_2024-06-11_1.pdf"
)
PU_REGS_RETRIEVED: Final[str] = "2026-08-08"

# --------------------------------------------------------------------------------------
# ERS-K power limits
# --------------------------------------------------------------------------------------

# VERIFIED — Art. 5.4.7: "The absolute electrical DC power of the ERS-K may not exceed
# 350kW." This is an absolute cap and applies to harvesting as well as deployment.
ERSK_MAX_POWER_W: Final[float] = 350_000.0

# VERIFIED — Art. 5.4.11: "The MGU-K mechanical torque magnitude may not exceed 500Nm."
MGUK_MAX_TORQUE_NM: Final[float] = 500.0

# VERIFIED — Art. 5.4.8(i). Propulsive electrical DC power limit in normal mode, as a
# piecewise-linear function of car speed in kph:
#     P(kW) = 1800 - 5  * v   for v < 340
#     P(kW) = 6900 - 20 * v   for 340 <= v < 345
#     P(kW) = 0               for v >= 345
# Combined with the 350 kW absolute cap of Art. 5.4.7, the effective curve is:
#     full 350 kW up to 290 kph  (1800 - 5*290 = 350)
#     linear taper 290 -> 340 kph, 350 kW -> 100 kW
#     steeper taper 340 -> 345 kph, 100 kW -> 0 kW
#     zero at and above 345 kph
#
# NOTE: this differs from the commonly repeated "tapers to zero at 355 km/h". 355 kph is
# the zero point for OVERRIDE mode (Art. 5.4.8(ii)), not normal mode. The project brief
# stated 290 -> 355 as a single linear ramp; the regulation text does not support that.
DEPLOY_TAPER_FULL_POWER_KPH: Final[float] = 290.0
DEPLOY_TAPER_KNEE_KPH: Final[float] = 340.0
DEPLOY_TAPER_ZERO_KPH: Final[float] = 345.0

# VERIFIED — Art. 5.4.8(ii). Override ("Manual Override Mode") propulsive limit:
#     P(kW) = 7100 - 20 * v   for v < 355
#     P(kW) = 0               for v >= 355
# With the 350 kW cap this holds full power to 337.5 kph.
OVERRIDE_FULL_POWER_KPH: Final[float] = 337.5
OVERRIDE_ZERO_KPH: Final[float] = 355.0

# --------------------------------------------------------------------------------------
# Energy store
# --------------------------------------------------------------------------------------

# VERIFIED — Art. 5.4.9: "The difference between the maximum and the minimum state of
# charge of the ES may not exceed 4MJ at any time the car is on the track."
# This is a usable *window*, not a physical cell capacity. The optimiser treats it as the
# usable capacity, which is the operative constraint for a single lap.
ES_USABLE_WINDOW_J: Final[float] = 4_000_000.0

# VERIFIED — Art. 5.4.13: ES stored energy may not be increased by more than 100 kJ while
# the car is stationary in the pit lane or garage during Qualifying.
ES_MAX_STATIONARY_RECHARGE_J: Final[float] = 100_000.0

# --------------------------------------------------------------------------------------
# Per-lap harvest limits
# --------------------------------------------------------------------------------------

# VERIFIED — Art. 5.4.10: harvest measured at the CU-K HV DC Bus "must not exceed 8.5MJ
# in each lap", reducible to 8 MJ at Competitions the FIA designates, plus up to 0.5 MJ
# additional per lap under the Sporting Regulations (the override allocation).
HARVEST_CAP_BASE_J: Final[float] = 8_500_000.0
HARVEST_CAP_REDUCED_J: Final[float] = 8_000_000.0
HARVEST_OVERRIDE_BONUS_J: Final[float] = 500_000.0

# SECONDARY — for 2026 the FIA lowered the qualifying-session harvest cap to 7 MJ, with
# discretion to reduce further but not below 5 MJ at circuits where the recovery
# strategies needed to reach the standard limit are excessive.
#   https://www.autosport.com/f1/news/
#     f1-melbourne-fia-cuts-recoverable-energy-in-qualifying-to-stop-extreme-tactics/10802294/
#   https://www.the-race.com/formula-1/f1s-new-energy-rankings-for-qualifying-revealed/
# Not confirmed against an FIA document — Issue 7 predates the change, and the
# per-Competition table lives in the Appendix to the Technical and Sporting Regulations,
# which has not been located. THIS PROJECT SOLVES A QUALIFYING LAP, so this cap, not the
# 8.5 MJ race figure, is the one that binds.
HARVEST_CAP_QUALIFYING_J: Final[float] = 7_000_000.0
HARVEST_CAP_QUALIFYING_FLOOR_J: Final[float] = 5_000_000.0

# Per-circuit qualifying caps have been reported but the figures are internally
# inconsistent with the 7 MJ baseline and are not used until verified against the FIA
# Appendix. Left deliberately empty rather than populated with unverified numbers.
HARVEST_CAP_QUALIFYING_BY_CIRCUIT: Final[dict[str, float]] = {}

# --------------------------------------------------------------------------------------
# Deployment power model
# --------------------------------------------------------------------------------------

Mode = Literal["normal", "override"]


def max_deploy_power_w(speed_kph: float, mode: Mode = "normal") -> float:
    """Maximum propulsive electrical DC power at a given car speed, in watts.

    Implements Art. 5.4.8 (speed-dependent propulsive limit) under the Art. 5.4.7
    absolute 350 kW cap. Returns 0.0 above the mode's cutoff speed.

    This is the regulatory ceiling, not a decision — the optimiser chooses how much of
    it to use. It is the reason energy spent at the top of a straight is wasted.
    """
    v = speed_kph
    if mode == "override":
        if v >= OVERRIDE_ZERO_KPH:
            return 0.0
        p_kw = 7100.0 - 20.0 * v
    else:
        if v >= DEPLOY_TAPER_ZERO_KPH:
            return 0.0
        p_kw = (1800.0 - 5.0 * v) if v < DEPLOY_TAPER_KNEE_KPH else (6900.0 - 20.0 * v)

    p_w = max(0.0, p_kw * 1000.0)
    return min(p_w, ERSK_MAX_POWER_W)


def deploy_taper_fraction(speed_kph: float, mode: Mode = "normal") -> float:
    """Fraction of the 350 kW cap still available at this speed, in [0, 1].

    Useful directly as an ML feature ("headroom to the taper").
    """
    return max_deploy_power_w(speed_kph, mode) / ERSK_MAX_POWER_W


# --------------------------------------------------------------------------------------
# Vehicle-level regulatory figures
# --------------------------------------------------------------------------------------

# SECONDARY — 2026 F1 Technical Regulations minimum car mass, excluding fuel, including
# driver. Reported widely as reduced from 800 kg to 768 kg. Not yet confirmed against the
# chassis technical regulations PDF (a separate document from the PU regulations above).
#   https://www.formula1.com/en/latest/article/the-beginners-guide-to-the-2026-regulations.6j0tS0hrHG2T01tpmK6XYz
MIN_CAR_MASS_KG: Final[float] = 768.0

# ASSUMPTION — fuel mass carried on a qualifying flying lap. Not a regulatory figure;
# teams run minimum fuel in qualifying. Sensitivity to this should be reported.
QUALIFYING_FUEL_MASS_KG: Final[float] = 10.0


PROVENANCE: Final[dict[str, str]] = {
    "pu_regulations": f"FIA 2026 F1 PU Technical Regulations, {PU_REGS_ISSUE}, {PU_REGS_DATE}",
    "pu_regulations_url": PU_REGS_URL,
    "retrieved": PU_REGS_RETRIEVED,
    "qualifying_harvest_cap": "SECONDARY (Autosport / The Race, 2026) — not FIA-confirmed",
    "min_car_mass": "SECONDARY (formula1.com) — not confirmed against chassis regulations",
}
