# Solar-Powered Irrigation System with Potential Energy Storage: Economic Feasibility and Reliability Analysis in Uzbekistan

An hourly-resolution Python simulation model for a solar PV irrigation pumping system in Uzbekistan, comparing two storage
technologies: 1. a lithium-ion battery and 2. an elevated-tank potential energy storage (PES) reservoir, plus 3. a hybrid 
design that uses both.

It quantifies the **reliability** of  the model (does the pump get enough energy when the crop needs water?) 
and the **economic feasibility** (CAPEX, NPV, IRR, payback, LCOE/LCOW) of each design.

## Why "potential energy storage"?

The surplus midday PV electricity is used to pump extra water into an elevated tank. When solar is insufficient during a 
scheduled irrigation event, that stored water is released **by gravity straight to the field**, meeting the water demand
without using any further electricity. 
It is, in effect, energy storage specific to the pumping load: "charging" (pumping efficiency), "discharging" (gravity flow).
`src/storage.py` implements this alongside a conventional battery model so the two can be compared on equal footing.

### Project structure

```
data/parameters.py     All model inputs, each with its source or assumption documented inline 
src/solar.py            Synthetic hourly solar resource (from monthly GHI) + PV output
src/demand.py            Cotton irrigation water demand -> hourly pump electrical load
src/storage.py           BatteryStorage and PotentialEnergyStorage (reservoir) classes
src/simulate.py          8,760-hour dispatch loop (3 strategies: battery-only / PES-only / hybrid)
src/economics.py         CAPEX/OPEX, NPV, IRR, payback, LCOE, LCOW
src/reliability.py       Monte Carlo LPSP distribution + storage-size sensitivity sweep
main.py                  Runs everything, writes plots + results_summary.md to outputs/
outputs/                 Generated after running main.py (plots, CSV, markdown report)
```


### Model outline

1. **Solar resource** (`solar.py`): monthly-average daily GHI is spread across daylight hours each day using latitude-dependent
   day length and a sine-shaped intraday profile, then perturbed with cloud-cover noise.
   PV output uses a performance-ratio model, `P = P_rated * GHI * PR`.

2. **Irrigation demand** (`demand.py`): a seasonal crop irrigation requirement (m3/ha, cotton) is distributed across the April–September
   growing season using a crop-coefficient-shaped monthly profile, then across a fixed daily watering schedule (early morning + early evening,
   independent of solar availability, which is what creates the generation/demand mismatch). Water volume is converted to electrical pump
   load via the standard hydraulic power equation.

3. **Dispatch simulation** (`simulate.py`): hour-by-hour, PV first serves the pump load directly; surplus charges storage; deficits are met first from
   the reservoir (gravity, "free" on discharge) and then the battery; anything still unmet is logged for the reliability metric (LPSP, Loss of
   Power Supply Probability).

4. **Economics** (`economics.py`): CAPEX by component, annual O&M, battery/pump replacement schedule, and "revenue" defined as the avoided cost of
   the energy actually served, valued at the grid tariff (or a diesel-genset cost if `grid_available=False`). Produces NPV, IRR (bisection solver),
   simple and discounted payback, LCOE ($/kWh) and LCOW ($/m3 delivered).

5. **Reliability** (`reliability.py`): a 20-run Monte Carlo re-simulation with different weather-noise seeds gives an LPSP *distribution*, not just
   a point estimate; a storage-sweep produces the classic reliability-vs-storage-size design curve for both technologies.

#### Key input data and sources (see `data/parameters.py` for the full list)


##### Headline result (default 5 ha / 6 kWp case)

The hybrid design reaches ~99% reliability (vs. ~63% battery-only, ~87% PES-only) but at higher CAPEX. 
None of the designs reach positive NPV within 25 years; grid power is simply very cheap. 
Completed numbers are in `outputs/results_summary.md`.

