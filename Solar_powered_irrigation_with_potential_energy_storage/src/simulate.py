"""
Hourly (8760-step) energy/water dispatch simulation for one representative
year. Implements three dispatch strategies so the battery-only and
potential-energy-storage-only systems can be benchmarked against a hybrid
design that uses both:

    "battery_only"  -- PV + battery, no elevated reservoir
    "pes_only"      -- PV + elevated reservoir, no battery
    "hybrid"        -- PV + reservoir (first) + battery (backup)

Dispatch logic per hour t
--------------------------
Let  pv(t)      = PV output (kW)
     load(t)    = pump electrical load required to deliver that hour's
                   scheduled irrigation water (kW)
     water(t)   = water volume required that hour (m3)

If pv(t) >= load(t):
    the load is met directly; surplus = pv(t) - load(t) charges storage
    (reservoir pumped up and/or battery charged, per the active strategy);
    anything storage cannot absorb is curtailed.

If pv(t) < load(t):
    deficit_kw = load(t) - pv(t), equivalent to a water shortfall
    deficit_m3 = deficit_kw / e_spec.
    1) the reservoir (if active) releases water by gravity to cover as much
       of deficit_m3 as it can -- this portion needs NO further electricity.
    2) any remaining electrical deficit is drawn from the battery (if active).
    3) whatever is still unmet is recorded as unmet demand (for the
       reliability / LPSP metric).
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from . import solar, demand
from .storage import BatteryStorage, PotentialEnergyStorage


def run_year_simulation(params: dict, year_index: int = 0) -> pd.DataFrame:
    ghi = solar.build_hourly_ghi(params)
    pv_kw = solar.pv_output_kw(ghi, params, year_index=year_index)
    water_m3 = demand.build_hourly_water_demand(params)
    load_kw = demand.build_hourly_pump_load_kw(water_m3, params)
    e_spec = demand.specific_pumping_energy_kwh_per_m3(params)

    strategy = params.get("dispatch_strategy", "hybrid")
    use_battery = strategy in ("battery_only", "hybrid")
    use_pes = strategy in ("pes_only", "hybrid")

    battery = BatteryStorage(
        capacity_kwh=params["battery_capacity_kwh"] if use_battery else 0.0,
        round_trip_eff=params["battery_round_trip_eff"],
        min_soc_frac=params["battery_min_soc"],
        max_c_rate=params["battery_max_c_rate"],
    )
    pes = PotentialEnergyStorage(
        capacity_m3=params["reservoir_capacity_m3"] if use_pes else 0.0,
        height_m=params["reservoir_height_m"],
        min_fill_frac=params["reservoir_min_fill_frac"],
        specific_pump_energy_kwh_per_m3=e_spec,
    )

    n = len(pv_kw)
    unmet_kwh = np.zeros(n)
    unmet_water_m3 = np.zeros(n)
    curtailed_kwh = np.zeros(n)
    battery_soc = np.zeros(n)
    reservoir_fill = np.zeros(n)
    served_from_pv = np.zeros(n)
    served_from_pes = np.zeros(n)
    served_from_battery = np.zeros(n)

    pv_arr = pv_kw.values
    load_arr = load_kw.values
    water_arr = water_m3.values

    for t in range(n):
        pv_t = pv_arr[t]
        load_t = load_arr[t]
        water_t = water_arr[t]

        if pv_t >= load_t:
            served_from_pv[t] = load_t
            surplus = pv_t - load_t
            if use_pes:
                used = pes.charge(surplus)
                surplus -= used
            if use_battery:
                used = battery.charge(surplus)
                surplus -= used
            curtailed_kwh[t] = max(surplus, 0.0)
        else:
            served_from_pv[t] = pv_t
            deficit_kw = load_t - pv_t
            deficit_m3 = deficit_kw / e_spec if e_spec > 0 else 0.0

            water_from_pes = pes.discharge_for_water(deficit_m3) if use_pes else 0.0
            served_from_pes[t] = water_from_pes * e_spec
            deficit_kw -= water_from_pes * e_spec

            battery_delivered = battery.discharge(deficit_kw) if use_battery else 0.0
            served_from_battery[t] = battery_delivered
            deficit_kw -= battery_delivered

            if deficit_kw > 1e-9:
                unmet_kwh[t] = deficit_kw
                unmet_water_m3[t] = deficit_kw / e_spec if e_spec > 0 else 0.0

        battery_soc[t] = battery.soc_frac()
        reservoir_fill[t] = pes.fill_frac()

    df = pd.DataFrame({
        "pv_kw": pv_arr,
        "load_kw": load_arr,
        "water_demand_m3": water_arr,
        "served_from_pv_kwh": served_from_pv,
        "served_from_pes_kwh": served_from_pes,
        "served_from_battery_kwh": served_from_battery,
        "unmet_kwh": unmet_kwh,
        "unmet_water_m3": unmet_water_m3,
        "curtailed_kwh": curtailed_kwh,
        "battery_soc_frac": battery_soc,
        "reservoir_fill_frac": reservoir_fill,
    }, index=pv_kw.index)

    return df


def summarize(df: pd.DataFrame, params: dict) -> dict:
    total_load_kwh = df["load_kw"].sum()
    total_water_m3 = df["water_demand_m3"].sum()
    served_kwh = (df["served_from_pv_kwh"] + df["served_from_pes_kwh"]
                  + df["served_from_battery_kwh"]).sum()
    unmet_kwh = df["unmet_kwh"].sum()
    unmet_water_m3 = df["unmet_water_m3"].sum()

    lpsp = unmet_kwh / total_load_kwh if total_load_kwh > 0 else 0.0  # Loss of Power Supply Probability
    lwsp = unmet_water_m3 / total_water_m3 if total_water_m3 > 0 else 0.0  # Loss of Water Supply Prob.

    n_deficit_hours = int((df["unmet_kwh"] > 1e-6).sum())
    n_irrigation_hours = int((df["load_kw"] > 1e-6).sum())

    return {
        "annual_pv_generation_kwh": float(df["pv_kw"].sum()),
        "annual_pump_load_kwh": float(total_load_kwh),
        "annual_water_demand_m3": float(total_water_m3),
        "served_pv_direct_kwh": float(df["served_from_pv_kwh"].sum()),
        "served_pes_kwh_equiv": float(df["served_from_pes_kwh"].sum()),
        "served_battery_kwh": float(df["served_from_battery_kwh"].sum()),
        "unmet_kwh": float(unmet_kwh),
        "unmet_water_m3": float(unmet_water_m3),
        "curtailed_kwh": float(df["curtailed_kwh"].sum()),
        "LPSP": float(lpsp),
        "loss_of_water_supply_probability": float(lwsp),
        "reliability_pct": float(1.0 - lpsp) * 100.0,
        "deficit_hours": n_deficit_hours,
        "irrigation_hours_per_year": n_irrigation_hours,
        "pct_hours_with_shortfall": 100.0 * n_deficit_hours / n_irrigation_hours if n_irrigation_hours else 0.0,
        "avg_battery_soc": float(df["battery_soc_frac"].mean()),
        "avg_reservoir_fill": float(df["reservoir_fill_frac"].mean()),
        "solar_fraction_pct": 100.0 * (served_kwh - df["served_from_battery_kwh"].sum()
                                        + 0) / total_load_kwh if total_load_kwh else 0.0,
    }
