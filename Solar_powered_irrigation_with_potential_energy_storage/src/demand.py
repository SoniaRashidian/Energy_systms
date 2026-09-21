"""
Converts the seasonal crop irrigation requirement (m3/ha, from CROPWAT-based
studies for cotton in Uzbekistan) into:
  1. an hourly water demand time series (m3/h), and
  2. the equivalent hourly electrical pumping load (kW) required to lift that
     water against the site's total dynamic head, at the specified daily
     irrigation schedule (irrigation_hours).

Wire-to-water specific energy
------------------------------
    e_pump [kWh/m3] = rho * g * H / (3.6e6 * eta_pump * eta_motor)

with rho = 1000 kg/m3, g = 9.81 m/s2, H = total dynamic head (m).
"""

from __future__ import annotations
import numpy as np
import pandas as pd

HOURS_PER_YEAR = 8760
RHO = 1000.0
G = 9.81


def specific_pumping_energy_kwh_per_m3(params: dict) -> float:
    H = params["total_dynamic_head_m"]
    eta = params["pump_efficiency"] * params["motor_efficiency"]
    return (RHO * G * H) / (3.6e6 * eta)


def build_hourly_water_demand(params: dict) -> pd.Series:
    """Return an 8760-length Series of water demand in m3/h."""

    days_in_month = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                      7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

    area_ha = params["farm_area_ha"]
    seasonal_req_m3_ha = params["seasonal_irrigation_requirement_m3_per_ha"]
    monthly_share = params["monthly_irrigation_share"]
    irrigation_hours = set(params["irrigation_hours"])

    total_seasonal_m3 = seasonal_req_m3_ha * area_ha

    idx = pd.date_range("2024-01-01", periods=HOURS_PER_YEAR, freq="h")
    water = np.zeros(HOURS_PER_YEAR)

    hour_ptr = 0
    for month in range(1, 13):
        n_days = days_in_month[month]
        month_total_m3 = total_seasonal_m3 * monthly_share.get(month, 0.0)
        daily_total_m3 = month_total_m3 / n_days if month_total_m3 > 0 else 0.0

        for _ in range(n_days):
            day_start = hour_ptr
            if daily_total_m3 > 0:
                # spread the day's water evenly across the scheduled irrigation hours
                n_hours_active = len(irrigation_hours)
                per_hour = daily_total_m3 / n_hours_active
                for h in range(24):
                    if h in irrigation_hours:
                        water[day_start + h] = per_hour
            hour_ptr += 24

    return pd.Series(water, index=idx, name="water_demand_m3")


def build_hourly_pump_load_kw(water_demand_m3: pd.Series, params: dict) -> pd.Series:
    """Convert hourly water demand (m3/h) to required electrical pump power (kW),
    assuming the full hourly water volume is delivered within that clock hour."""
    e_spec = specific_pumping_energy_kwh_per_m3(params)  # kWh/m3
    load_kw = water_demand_m3.values * e_spec  # kWh delivered in 1 h == kW
    return pd.Series(load_kw, index=water_demand_m3.index, name="pump_load_kw")


def annual_water_and_energy(params: dict) -> dict:
    water = build_hourly_water_demand(params)
    load = build_hourly_pump_load_kw(water, params)
    return {
        "annual_water_m3": float(water.sum()),
        "annual_pumping_energy_kwh": float(load.sum()),
        "specific_energy_kwh_per_m3": specific_pumping_energy_kwh_per_m3(params),
    }
