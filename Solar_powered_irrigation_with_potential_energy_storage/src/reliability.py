"""
Two complementary reliability analyses beyond the single deterministic run in
simulate.py:

1. monte_carlo_lpsp(): re-runs the hourly dispatch simulation N times with a
   different random cloud-cover seed each time, to get a distribution (not
   just a point estimate) of the Loss of Power Supply Probability (LPSP) and
   Loss of Water Supply Probability (LWSP). This captures year-to-year
   weather variability risk, which a single deterministic run hides.

2. storage_sweep(): varies battery size and/or reservoir size and reports the
   resulting LPSP for each, producing the data behind a reliability-vs-storage
   design curve (the classic sizing chart for stand-alone renewable systems).
"""

from __future__ import annotations
import copy
import numpy as np
import pandas as pd

from . import simulate


def monte_carlo_lpsp(params: dict, n_runs: int = 20) -> pd.DataFrame:
    rows = []
    for i in range(n_runs):
        p = copy.deepcopy(params)
        p["random_seed"] = 1000 + i
        df = simulate.run_year_simulation(p, year_index=0)
        s = simulate.summarize(df, p)
        rows.append({
            "run": i,
            "LPSP": s["LPSP"],
            "loss_of_water_supply_probability": s["loss_of_water_supply_probability"],
            "unmet_kwh": s["unmet_kwh"],
            "annual_pv_generation_kwh": s["annual_pv_generation_kwh"],
        })
    return pd.DataFrame(rows)


def storage_sweep(params: dict, battery_sizes_kwh=None, reservoir_sizes_m3=None) -> pd.DataFrame:
    """Vary storage sizes (independently, holding the other technology's size at
    the base-case value) and report LPSP for each, under the hybrid strategy."""

    if battery_sizes_kwh is None:
        battery_sizes_kwh = [0, 5, 10, 15, 20, 30, 40]
    if reservoir_sizes_m3 is None:
        reservoir_sizes_m3 = [0, 25, 50, 100, 150, 250, 400]

    rows = []
    for b in battery_sizes_kwh:
        p = copy.deepcopy(params)
        p["dispatch_strategy"] = "hybrid"
        p["battery_capacity_kwh"] = b
        df = simulate.run_year_simulation(p, year_index=0)
        s = simulate.summarize(df, p)
        rows.append({"sweep": "battery_kwh", "value": b, "LPSP": s["LPSP"],
                      "reliability_pct": s["reliability_pct"]})

    for res in reservoir_sizes_m3:
        p = copy.deepcopy(params)
        p["dispatch_strategy"] = "hybrid"
        p["reservoir_capacity_m3"] = res
        df = simulate.run_year_simulation(p, year_index=0)
        s = simulate.summarize(df, p)
        rows.append({"sweep": "reservoir_m3", "value": res, "LPSP": s["LPSP"],
                      "reliability_pct": s["reliability_pct"]})

    return pd.DataFrame(rows)
