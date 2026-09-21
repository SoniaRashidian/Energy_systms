"""
Standard project-finance metrics for the solar irrigation system, benchmarked
against the "do nothing new" baseline of pumping the same water with
grid electricity (or a diesel genset if params["grid_available"] is False).

Outputs
-------
  CAPEX breakdown (PV, pump, battery, reservoir, balance of system)
  Annual O&M
  Replacement schedule (battery, pump)
  Annual avoided-cost "revenue" (grid tariff x energy actually served)
  NPV, discounted payback period, simple payback period, IRR
  LCOE ($/kWh delivered) and LCOW ($/m3 water delivered)
"""

from __future__ import annotations
import numpy as np


def capex_breakdown(params: dict) -> dict:
    pv_capex = params["pv_capacity_kwp"] * params["pv_capex_usd_per_kwp"]

    # pump electrical rating sized to cover peak instantaneous load with margin
    pump_kw_rating = params["pv_capacity_kwp"]  # conservative: pump sized to array
    pump_capex = pump_kw_rating * params["pump_capex_usd_per_kw_elec"]

    use_battery = params.get("dispatch_strategy", "hybrid") in ("battery_only", "hybrid")
    use_pes = params.get("dispatch_strategy", "hybrid") in ("pes_only", "hybrid")

    battery_capex = params["battery_capacity_kwh"] * params["battery_capex_usd_per_kwh"] if use_battery else 0.0
    reservoir_capex = params["reservoir_capacity_m3"] * params["reservoir_capex_usd_per_m3"] if use_pes else 0.0

    subtotal = pv_capex + pump_capex + battery_capex + reservoir_capex
    bos = subtotal * params["balance_of_system_pct"]
    total = subtotal + bos

    return {
        "pv_capex_usd": pv_capex,
        "pump_capex_usd": pump_capex,
        "battery_capex_usd": battery_capex,
        "reservoir_capex_usd": reservoir_capex,
        "balance_of_system_usd": bos,
        "total_capex_usd": total,
    }


def annual_om_usd(params: dict, capex: dict) -> float:
    om = (capex["pv_capex_usd"] * params["pv_om_pct_of_capex_per_yr"]
          + capex["pump_capex_usd"] * params["pump_om_pct_of_capex_per_yr"]
          + capex["battery_capex_usd"] * params["battery_om_pct_of_capex_per_yr"]
          + capex["reservoir_capex_usd"] * params["reservoir_om_pct_of_capex_per_yr"])
    return om


def grid_tariff_usd_per_kwh(params: dict) -> float:
    return params["grid_tariff_uzs_per_kwh"] / params["usd_uzs_exchange_rate"]


def baseline_unit_cost_usd_per_kwh(params: dict) -> float:
    """Cost of the avoided alternative: grid tariff, or diesel genset cost if no grid."""
    if params.get("grid_available", True):
        return grid_tariff_usd_per_kwh(params)
    fuel_cost = params["diesel_price_usd_per_l"] * params["diesel_genset_l_per_kwh"]
    return fuel_cost + params["diesel_om_usd_per_kwh"]


def replacement_schedule(params: dict, capex: dict) -> dict:
    """Year -> USD of replacement capex, for components with lifetime < project horizon."""
    horizon = params["project_lifetime_yr"]
    schedule: dict[int, float] = {}

    def add(cost, lifetime, key_cost):
        if lifetime <= 0 or lifetime >= horizon or cost <= 0:
            return
        y = lifetime
        while y < horizon:
            schedule[y] = schedule.get(y, 0.0) + cost
            y += lifetime

    add(capex["battery_capex_usd"], params.get("battery_lifetime_yr", 999), "battery")
    add(capex["pump_capex_usd"], params.get("pump_lifetime_yr", 999), "pump")
    return schedule


def evaluate_project(params: dict, annual_served_kwh_year0: float,
                      annual_water_m3_year0: float) -> dict:
    """Full economic evaluation given the first-year energy actually served by the
    system (from the hourly simulation)."""

    capex = capex_breakdown(params)
    total_capex = capex["total_capex_usd"]
    om0 = annual_om_usd(params, capex)
    replacements = replacement_schedule(params, capex)

    r = params["discount_rate_real"]
    horizon = params["project_lifetime_yr"]
    tariff0 = baseline_unit_cost_usd_per_kwh(params)
    tariff_escalation = params.get("grid_tariff_escalation_pct_per_yr", 0.0)
    pv_degr = params.get("pv_degradation_pct_per_yr", 0.0)

    cashflows = np.zeros(horizon + 1)
    cashflows[0] = -total_capex

    disc_energy_kwh = 0.0
    disc_water_m3 = 0.0
    disc_costs_usd = total_capex

    yearly_rows = []
    for y in range(1, horizon + 1):
        served_kwh = annual_served_kwh_year0 * (1.0 - pv_degr) ** (y - 1)
        water_m3 = annual_water_m3_year0 * (1.0 - pv_degr) ** (y - 1)
        tariff_y = tariff0 * (1.0 + tariff_escalation) ** (y - 1)

        savings = served_kwh * tariff_y
        om_cost = om0 * (1.0 + params.get("inflation_rate", 0.0) * 0)  # keep O&M in real terms
        capex_repl = replacements.get(y, 0.0)

        net_cf = savings - om_cost - capex_repl
        cashflows[y] = net_cf

        disc_factor = 1.0 / (1.0 + r) ** y
        disc_energy_kwh += served_kwh * disc_factor
        disc_water_m3 += water_m3 * disc_factor
        disc_costs_usd += (om_cost + capex_repl) * disc_factor

        yearly_rows.append({
            "year": y, "served_kwh": served_kwh, "savings_usd": savings,
            "om_usd": om_cost, "capex_replacement_usd": capex_repl,
            "net_cashflow_usd": net_cf,
        })

    npv = float(np.sum(cashflows / (1.0 + r) ** np.arange(horizon + 1)))
    irr = _irr(cashflows)

    lcoe = disc_costs_usd / disc_energy_kwh if disc_energy_kwh > 0 else float("nan")
    lcow = disc_costs_usd / disc_water_m3 if disc_water_m3 > 0 else float("nan")

    cum = np.cumsum(cashflows)
    simple_payback = _first_crossing(cum)
    disc_cum = np.cumsum(cashflows / (1.0 + r) ** np.arange(horizon + 1))
    discounted_payback = _first_crossing(disc_cum)

    return {
        "capex": capex,
        "annual_om_usd_year0": om0,
        "replacement_schedule": replacements,
        "baseline_unit_cost_usd_per_kwh": tariff0,
        "npv_usd": npv,
        "irr_pct": irr * 100.0 if irr is not None else None,
        "lcoe_usd_per_kwh": lcoe,
        "lcow_usd_per_m3": lcow,
        "simple_payback_yr": simple_payback,
        "discounted_payback_yr": discounted_payback,
        "yearly_cashflows": yearly_rows,
        "raw_cashflow_usd": cashflows,
    }


def _first_crossing(cum_series: np.ndarray):
    """Return the (linearly interpolated) year index where a cumulative cashflow
    series first crosses from negative to non-negative, or None if it never does."""
    for i in range(1, len(cum_series)):
        if cum_series[i - 1] < 0 <= cum_series[i]:
            prev, cur = cum_series[i - 1], cum_series[i]
            frac = -prev / (cur - prev) if (cur - prev) != 0 else 0.0
            return (i - 1) + frac
    return None


def _irr(cashflows: np.ndarray, lo: float = -0.5, hi: float = 2.0, tol: float = 1e-6):
    """Bisection IRR solver (avoids requiring numpy_financial)."""
    def npv_at(rate):
        return float(np.sum(cashflows / (1.0 + rate) ** np.arange(len(cashflows))))

    f_lo, f_hi = npv_at(lo), npv_at(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None  # IRR not found in range
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv_at(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0
