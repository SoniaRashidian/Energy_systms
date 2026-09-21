"""
Two storage technologies, both exposed through the same charge/discharge
interface so the dispatch loop in simulate.py can treat them uniformly:

  BatteryStorage
      Standard electrochemical Li-ion storage. State of charge tracked in kWh.

  PotentialEnergyStorage (PES)
      An elevated tank/reservoir. Surplus PV electricity is spent pumping
      water up into the tank (this is itself a pumping load, subject to the
      same wire-to-water efficiency as normal irrigation pumping). Stored
      water is later released by gravity straight to the field, which
      *directly meets a water/energy demand* without drawing any further
      electricity -- i.e. it discharges as "avoided pumping energy" at
      effectively 100% conversion efficiency (gravity flow), though the
      *charging* leg still incurs the pump's electrical efficiency losses.
      State of charge tracked in m3 (and reported in kWh-equivalent for
      comparison with the battery).
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np

RHO = 1000.0
G = 9.81


@dataclass
class BatteryStorage:
    capacity_kwh: float
    round_trip_eff: float
    min_soc_frac: float
    max_c_rate: float
    soc_kwh: float = None  # type: ignore

    def __post_init__(self):
        if self.soc_kwh is None:
            self.soc_kwh = self.capacity_kwh * self.min_soc_frac

    @property
    def usable_capacity_kwh(self) -> float:
        return self.capacity_kwh * (1.0 - self.min_soc_frac)

    @property
    def max_power_kw(self) -> float:
        return self.capacity_kwh * self.max_c_rate

    def charge(self, surplus_kwh: float) -> float:
        """Accept up to max_power_kw of surplus energy this hour. Returns energy
        actually absorbed (pre-loss, i.e. taken from the surplus)."""
        if surplus_kwh <= 0:
            return 0.0
        chargeable = min(surplus_kwh, self.max_power_kw)
        eta_c = np.sqrt(self.round_trip_eff)  # split RTE evenly across charge/discharge
        headroom_kwh = self.capacity_kwh - self.soc_kwh
        energy_in = min(chargeable, headroom_kwh / eta_c) if eta_c > 0 else 0.0
        self.soc_kwh += energy_in * eta_c
        return energy_in

    def discharge(self, deficit_kwh: float) -> float:
        """Deliver up to max_power_kw to cover a deficit this hour. Returns energy
        actually delivered to the load."""
        if deficit_kwh <= 0:
            return 0.0
        eta_d = np.sqrt(self.round_trip_eff)
        available_kwh = max(0.0, self.soc_kwh - self.capacity_kwh * self.min_soc_frac)
        deliverable = min(deficit_kwh, self.max_power_kw, available_kwh * eta_d)
        self.soc_kwh -= deliverable / eta_d if eta_d > 0 else 0.0
        return deliverable

    def soc_frac(self) -> float:
        return self.soc_kwh / self.capacity_kwh if self.capacity_kwh > 0 else 0.0


@dataclass
class PotentialEnergyStorage:
    capacity_m3: float
    height_m: float
    min_fill_frac: float
    specific_pump_energy_kwh_per_m3: float   # cost of pumping INTO the reservoir
    max_charge_kw: float = 1e9               # optional power limit (pump size), default unconstrained
    volume_m3: float = None  # type: ignore

    def __post_init__(self):
        if self.volume_m3 is None:
            self.volume_m3 = self.capacity_m3 * self.min_fill_frac

    def energy_equivalent_kwh(self) -> float:
        """Gravitational PE of the currently stored volume, in kWh (informational --
        this is NOT what discharging returns as electricity; it is returned as
        gravity-fed water, i.e. avoided pumping energy)."""
        return RHO * G * self.height_m * self.volume_m3 / 3.6e6

    def charge(self, surplus_kwh: float) -> float:
        """Use surplus PV electricity to pump extra water into the tank.
        Returns the electrical energy actually consumed."""
        if surplus_kwh <= 0 or self.specific_pump_energy_kwh_per_m3 <= 0:
            return 0.0
        elec_available = min(surplus_kwh, self.max_charge_kw)
        max_volume_from_energy = elec_available / self.specific_pump_energy_kwh_per_m3
        headroom_m3 = self.capacity_m3 - self.volume_m3
        volume_added = min(max_volume_from_energy, headroom_m3)
        elec_used = volume_added * self.specific_pump_energy_kwh_per_m3
        self.volume_m3 += volume_added
        return elec_used

    def discharge_for_water(self, water_deficit_m3: float) -> float:
        """Release stored water by gravity to directly meet a water demand.
        Returns the volume actually supplied (m3). This offsets an equivalent
        electrical pumping requirement of volume * specific_pump_energy at the
        point this is used in the dispatch loop."""
        if water_deficit_m3 <= 0:
            return 0.0
        available_m3 = max(0.0, self.volume_m3 - self.capacity_m3 * self.min_fill_frac)
        supplied = min(water_deficit_m3, available_m3)
        self.volume_m3 -= supplied
        return supplied

    def fill_frac(self) -> float:
        return self.volume_m3 / self.capacity_m3 if self.capacity_m3 > 0 else 0.0
