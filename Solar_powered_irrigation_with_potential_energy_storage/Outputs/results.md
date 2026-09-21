# Solar-Powered Irrigation with Potential Energy Storage -- Results

Site: Uzbekistan (default site parameters ~ Bukhara/Navoi region, lat 39.8°N, annual GHI 1950 kWh/m2/yr)

Farm area: 5.0 ha | Crop: cotton | PV array: 6.0 kWp


## System design comparison

| Design | Annual PV (kWh) | Reliability (%) | LPSP (%) | Unmet water (m3) | CAPEX (USD) | NPV (USD) | IRR (%) | Simple payback (yr) | LCOE (USD/kWh) | LCOW (USD/m3) |
|---|---|---|---|---|---|---|---|---|---|---|
| Battery only | 8788 | 63.15 | 36.85 | 12530 | 8,800 | -9,831 | n/a | >25 | 0.566 | 0.042 |
| Potential-energy storage only | 8788 | 87.36 | 12.64 | 4297 | 13,365 | -12,172 | -6.4 | >25 | 0.519 | 0.053 |
| Hybrid (PES + battery) | 8788 | 98.88 | 1.12 | 382 | 16,225 | -16,429 | -14.7 | >25 | 0.596 | 0.069 |
| Hybrid vs. diesel baseline | 8788 | 98.88 | 1.12 | 382 | 16,225 | -7,593 | 4.4 | 17.2 | 0.596 | 0.069 |

## Monte Carlo reliability (hybrid design, 20 synthetic weather years)

- Mean LPSP: 1.04% (std 0.06 pp, range 0.92-1.19%)

## Storage sizing sensitivity (hybrid design)


**Battery size vs reliability**

| Size | Reliability (%) |
|---|---|
| 0 | 87.36 |
| 5 | 95.47 |
| 10 | 98.88 |
| 15 | 99.78 |
| 20 | 99.95 |
| 30 | 100.00 |
| 40 | 100.00 |

**Reservoir size vs reliability**

| Size | Reliability (%) |
|---|---|
| 0 | 63.15 |
| 25 | 72.62 |
| 50 | 79.28 |
| 100 | 92.09 |
| 150 | 98.88 |
| 250 | 100.00 |
| 400 | 100.00 |
