"""
Builds an 8,760-hour synthetic solar resource time series for the site from
monthly-average daily GHI data (see data/parameters.py), then converts it to
PV array AC output.

Method
======
1. For each day of the year, allocate that month's average daily GHI (kWh/m2)
   across daylight hours using a sine-squared bell curve, whose width is set
   by the day length computed from solar declination at the site latitude.
   This reproduces the seasonal swing in both irradiance *and* day length that
   drives the generation/demand mismatch central to the reliability analysis.
2. Add stochastic cloud-cover noise (log-normal-ish multiplicative noise,
   clipped >=0) so the resulting time series isn't perfectly smooth -- this
   matters for the reliability (LPSP) results, not just the average energy
   balance.
3. Convert irradiance -> PV output using a simple performance-ratio model:
       P_pv(t) [kW] = P_rated_kWp * (GHI(t) / 1 kW/m2) * PR
   which is standard practice for first-pass feasibility studies (equivalent
   to NREL PVWatts' simplified mode) and appropriate given the accuracy of the
   underlying monthly GHI data.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

HOURS_PER_YEAR = 8760


def day_length_hours(day_of_year: int, latitude_deg: float) -> float:
    """Approximate day length (sunrise-to-sunset) in hours from solar declination."""
    lat = np.radians(latitude_deg)
    decl = np.radians(23.45) * np.sin(np.radians(360.0 / 365.0 * (284 + day_of_year)))
    cos_h = -np.tan(lat) * np.tan(decl)
    cos_h = np.clip(cos_h, -1.0, 1.0)
    hour_angle = np.degrees(np.arccos(cos_h))
    return 2.0 * hour_angle / 15.0


def build_hourly_ghi(params: dict) -> pd.Series:
    """Return an 8760-length pandas Series of hourly GHI in kWh/m2 (= kW/m2 average
    over the hour), indexed 0..8759, for a non-leap representative year."""

    rng = np.random.default_rng(params.get("random_seed", 42))
    lat = params["latitude_deg"]
    annual_ghi = params["annual_ghi_kwh_m2"]
    monthly_share = params["monthly_ghi_share"]
    noise_std = params.get("ghi_hourly_noise_std", 0.12)

    days_in_month = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                      7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

    idx = pd.date_range("2024-01-01", periods=HOURS_PER_YEAR, freq="h")
    ghi = np.zeros(HOURS_PER_YEAR)

    doy = 0
    for month in range(1, 13):
        n_days = days_in_month[month]
        month_total_ghi = annual_ghi * monthly_share[month]
        daily_avg_ghi = month_total_ghi / n_days  # kWh/m2/day for this month

        for _ in range(n_days):
            doy += 1
            dl = day_length_hours(doy, lat)  # hours
            sunrise = 12.0 - dl / 2.0
            sunset = 12.0 + dl / 2.0

            hours_today = np.arange(24)
            profile = np.zeros(24)
            daylight_mask = (hours_today >= np.floor(sunrise)) & (hours_today <= np.ceil(sunset))
            # sine-squared bell curve over the daylight window, zero outside it
            frac_of_day = (hours_today[daylight_mask] + 0.5 - sunrise) / dl
            frac_of_day = np.clip(frac_of_day, 0, 1)
            shape = np.sin(np.pi * frac_of_day) ** 1.0
            shape[shape < 0] = 0.0
            if shape.sum() > 0:
                profile[daylight_mask] = shape / shape.sum() * daily_avg_ghi

            day_start = (doy - 1) * 24
            ghi[day_start:day_start + 24] = profile

    # multiplicative cloud-cover noise, only where there is sun
    noise = rng.normal(loc=1.0, scale=noise_std, size=HOURS_PER_YEAR)
    noise = np.clip(noise, 0.0, 1.8)
    ghi_noisy = np.where(ghi > 0, ghi * noise, 0.0)

    return pd.Series(ghi_noisy, index=idx, name="ghi_kwh_m2")


def pv_output_kw(ghi_series: pd.Series, params: dict, year_index: int = 0) -> pd.Series:
    """Convert hourly GHI (kWh/m2, i.e. average kW/m2 over the hour) to PV AC power (kW),
    applying the performance ratio and (optionally) cumulative annual degradation."""

    p_rated = params["pv_capacity_kwp"]
    pr = params["pv_performance_ratio"]
    degr = params.get("pv_degradation_pct_per_yr", 0.0)
    degradation_factor = (1.0 - degr) ** year_index

    p_kw = p_rated * ghi_series.values * pr * degradation_factor
    return pd.Series(p_kw, index=ghi_series.index, name="pv_kw")


def annual_pv_energy_kwh(params: dict) -> float:
    """Quick scalar estimate of first-year PV energy yield (kWh/yr), useful for sizing."""
    ghi = build_hourly_ghi(params)
    p = pv_output_kw(ghi, params)
    return float(p.sum())
