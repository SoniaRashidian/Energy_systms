"""
Produces (in outputs/):
    results_summary.md          - headline numbers for all three system designs
    timeseries_sample_week.png  - PV / load / storage behaviour, sample summer week
    storage_sensitivity.png     - LPSP vs battery size and vs reservoir size
    cashflow.png                - cumulative discounted cash flow, all designs
    monte_carlo_lpsp.png        - reliability distribution under weather variability
    input_parameters.csv        - fully documented input dataset (for the report)
"""

from __future__ import annotations
import os
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data.parameters import build_parameters
from src import simulate, economics, reliability

OUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUT_DIR, exist_ok=True)


def export_input_parameters(params: dict):
    rows = [{"parameter": k, "value": v} for k, v in params.items()
            if not isinstance(v, dict)]
    for k, v in params.items():
        if isinstance(v, dict):
            rows.append({"parameter": k, "value": json.dumps(v)})
    pd.DataFrame(rows).sort_values("parameter").to_csv(
        os.path.join(OUT_DIR, "input_parameters.csv"), index=False)


def run_design(params_base: dict, strategy: str) -> dict:
    p = dict(params_base)
    p["dispatch_strategy"] = strategy
    df = simulate.run_year_simulation(p, year_index=0)
    summary = simulate.summarize(df, p)
    served_kwh = (summary["served_pv_direct_kwh"] + summary["served_pes_kwh_equiv"]
                  + summary["served_battery_kwh"])
    econ = economics.evaluate_project(p, served_kwh, summary["annual_water_demand_m3"])
    return {"params": p, "timeseries": df, "summary": summary, "economics": econ}


def plot_sample_week(results: dict, out_path: str):
    fig, axes = plt.subplots(len(results), 1, figsize=(11, 3.2 * len(results)), sharex=True)
    if len(results) == 1:
        axes = [axes]
    
    start, end = 24 * 190, 24 * 197
    for ax, (name, res) in zip(axes, results.items()):
        df = res["timeseries"].iloc[start:end]
        ax.plot(df.index, df["pv_kw"], label="PV output (kW)", color="#e69f00")
        ax.plot(df.index, df["load_kw"], label="Pump load required (kW)", color="#333333", ls="--")
        ax.fill_between(df.index, 0, df["unmet_kwh"], color="red", alpha=0.4, label="Unmet demand (kWh)")
        ax2 = ax.twinx()
        ax2.plot(df.index, df["battery_soc_frac"] * 100, color="#0072b2", alpha=0.7, label="Battery SoC (%)")
        ax2.plot(df.index, df["reservoir_fill_frac"] * 100, color="#009e73", alpha=0.7, label="Reservoir fill (%)")
        ax2.set_ylim(0, 105)
        ax.set_title(f"{name} -- sample summer week (mid-July)")
        ax.set_ylabel("kW")
        ax2.set_ylabel("Storage state (%)")
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_storage_sensitivity(params: dict, out_path: str):
    sweep = reliability.storage_sweep(params)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, key, xlabel in zip(
        axes, ["battery_kwh", "reservoir_m3"],
        ["Battery capacity (kWh)", "Reservoir capacity (m3)"]
    ):
        sub = sweep[sweep["sweep"] == key]
        ax.plot(sub["value"], sub["reliability_pct"], marker="o", color="#0072b2")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Reliability (% of pump-energy demand served)")
        ax.set_title(f"Reliability vs {xlabel.split(' (')[0]}")
        ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close(fig)
    return sweep


def plot_cashflow(results: dict, out_path: str):
    fig, ax = plt.subplots(figsize=(9, 5))
    for name, res in results.items():
        cf = res["economics"]["raw_cashflow_usd"]
        r = res["params"]["discount_rate_real"]
        disc_cum = (cf / (1 + r) ** pd.Series(range(len(cf)))).cumsum()
        ax.plot(range(len(cf)), disc_cum, marker=".", label=name)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Project year")
    ax.set_ylabel("Cumulative discounted cash flow (USD)")
    ax.set_title("Discounted cash flow by system design")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_monte_carlo(params: dict, out_path: str):
    mc = reliability.monte_carlo_lpsp(params, n_runs=20)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(mc["LPSP"] * 100, bins=10, color="#cc79a7", edgecolor="black")
    ax.set_xlabel("Loss of Power Supply Probability (%)")
    ax.set_ylabel("Number of simulated years (of 20)")
    ax.set_title("Reliability under weather-variability Monte Carlo (hybrid design)")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close(fig)
    return mc


def write_report(results: dict, sweep: pd.DataFrame, mc: pd.DataFrame, params: dict):
    lines = []
    lines.append("# Solar-Powered Irrigation with Potential Energy Storage -- Results\n")
    lines.append("Site: Uzbekistan (default site parameters ~ Bukhara/Navoi region, "
                  f"lat {params['latitude_deg']}°N, annual GHI {params['annual_ghi_kwh_m2']:.0f} kWh/m2/yr)\n")
    lines.append(f"Farm area: {params['farm_area_ha']} ha | Crop: cotton | "
                 f"PV array: {params['pv_capacity_kwp']} kWp\n")

    lines.append("\n## System design comparison\n")
    lines.append("| Design | Annual PV (kWh) | Reliability (%) | LPSP (%) | "
                  "Unmet water (m3) | CAPEX (USD) | NPV (USD) | IRR (%) | "
                  "Simple payback (yr) | LCOE (USD/kWh) | LCOW (USD/m3) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, res in results.items():
        s, e = res["summary"], res["economics"]
        irr_str = f"{e['irr_pct']:.1f}" if e["irr_pct"] is not None else "n/a"
        pb_str = f"{e['simple_payback_yr']:.1f}" if e["simple_payback_yr"] is not None else ">25"
        lines.append(
            f"| {name} | {s['annual_pv_generation_kwh']:.0f} | {s['reliability_pct']:.2f} | "
            f"{100*s['LPSP']:.2f} | {s['unmet_water_m3']:.0f} | "
            f"{e['capex']['total_capex_usd']:,.0f} | {e['npv_usd']:,.0f} | {irr_str} | "
            f"{pb_str} | {e['lcoe_usd_per_kwh']:.3f} | {e['lcow_usd_per_m3']:.3f} |"
        )

    lines.append("\n## Monte Carlo reliability (hybrid design, 20 synthetic weather years)\n")
    lines.append(f"- Mean LPSP: {mc['LPSP'].mean()*100:.2f}% "
                 f"(std {mc['LPSP'].std()*100:.2f} pp, "
                 f"range {mc['LPSP'].min()*100:.2f}-{mc['LPSP'].max()*100:.2f}%)")

    lines.append("\n## Storage sizing sensitivity (hybrid design)\n")
    for key, label in [("battery_kwh", "Battery"), ("reservoir_m3", "Reservoir")]:
        sub = sweep[sweep["sweep"] == key].sort_values("value")
        lines.append(f"\n**{label} size vs reliability**\n")
        lines.append("| Size | Reliability (%) |")
        lines.append("|---|---|")
        for _, row in sub.iterrows():
            lines.append(f"| {row['value']:.0f} | {row['reliability_pct']:.2f} |")

    with open(os.path.join(OUT_DIR, "results_summary.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    params = build_parameters()
    export_input_parameters(params)

    strategies = {
        "Battery only": "battery_only",
        "Potential-energy storage only": "pes_only",
        "Hybrid (PES + battery)": "hybrid",
    }

    results = {name: run_design(params, strat) for name, strat in strategies.items()}

    # Secondary case: same hybrid design, but benchmarked against a diesel-genset
    # baseline instead of grid electricity -- realistic for farms without a grid
    # connection, and a common real-world driver for solar pumping adoption.
    diesel_params = dict(params)
    diesel_params["grid_available"] = False
    results["Hybrid vs. diesel baseline"] = run_design(diesel_params, "hybrid")

    print("\n=== Design comparison ===")
    for name, res in results.items():
        s, e = res["summary"], res["economics"]
        print(f"\n--- {name} ---")
        print(f"  Reliability: {s['reliability_pct']:.2f}%  (LPSP {100*s['LPSP']:.2f}%)")
        print(f"  Unmet water: {s['unmet_water_m3']:.0f} m3/yr of "
              f"{s['annual_water_demand_m3']:.0f} m3/yr required")
        print(f"  CAPEX: ${e['capex']['total_capex_usd']:,.0f}")
        print(f"  NPV ({params['project_lifetime_yr']} yr, {params['discount_rate_real']*100:.0f}% discount): "
              f"${e['npv_usd']:,.0f}")
        print(f"  IRR: {e['irr_pct']:.1f}%" if e['irr_pct'] is not None else "  IRR: not found in [-50%, 200%]")
        print(f"  Simple payback: {e['simple_payback_yr']:.1f} yr" if e['simple_payback_yr'] is not None
              else "  Simple payback: beyond project horizon")
        print(f"  LCOE: ${e['lcoe_usd_per_kwh']:.3f}/kWh   LCOW: ${e['lcow_usd_per_m3']:.3f}/m3")

    dispatch_results = {k: v for k, v in results.items() if k in strategies}
    plot_sample_week(dispatch_results, os.path.join(OUT_DIR, "timeseries_sample_week.png"))
    sweep = plot_storage_sensitivity(params, os.path.join(OUT_DIR, "storage_sensitivity.png"))
    plot_cashflow(results, os.path.join(OUT_DIR, "cashflow.png"))
    mc = plot_monte_carlo(params, os.path.join(OUT_DIR, "monte_carlo_lpsp.png"))

    write_report(results, sweep, mc, params)
    print(f"\nAll outputs written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
