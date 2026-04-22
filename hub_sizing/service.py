"""
Stub service time distribution for a single landing pad.

A landing pad is "busy" from the moment a drone touches down until it lifts off
for its next delivery. The service time S breaks into four sequential phases:

    S = t_approach + t_unload + t_battery_swap + t_load_next

Phase breakdown (stub values)
------------------------------
t_approach      ~30 s    drone descends from cruise altitude, touches down
t_unload        ~60 s    package removed by kiosk operator / automated arm
t_battery_swap  ~180 s   depleted battery out, charged pack in
t_load_next     ~60 s    next order loaded, pre-flight check

Total E[S] ≈ 330 s (5.5 min) — conservative for a manual kiosk operator.
An automated swap system (DJI Dock style) could halve this to ~165 s.

For M/G/k we need E[S] and c_s² = Var[S] / E[S]²
c_s² = 1.0 → exponential (recovers M/M/k, simplest case)
c_s² < 1 → more regular (e.g., deterministic battery swap robot)
c_s² > 1 → high variance (e.g., manual, weather delays)

Missing inputs
--------------
- Measured swap times from a prototype or vendor spec sheet
- Variance data (does the swap always take the same time?)
- Whether kiosk is staffed, semi-automated, or fully automated
"""

from dataclasses import dataclass

from settings.service import (
    APPROACH_S,
    UNLOAD_S,
    BATTERY_SWAP_S,
    LOAD_NEXT_S,
    AUTOMATED_BATTERY_SWAP_S,
    CV_SQUARED,
    AUTOMATED_CV_SQUARED,
)


@dataclass
class ServiceSpec:
    mean_s: float           # E[S]
    cv_squared: float       # c_s²  = Var[S] / E[S]²
    is_stub: bool = True

    @property
    def mean_min(self) -> float:
        return self.mean_s / 60.0

    @property
    def variance_s2(self) -> float:
        return self.cv_squared * (self.mean_s ** 2)


def default_service_spec() -> ServiceSpec:
    mean = APPROACH_S + UNLOAD_S + BATTERY_SWAP_S + LOAD_NEXT_S
    return ServiceSpec(mean_s=mean, cv_squared=CV_SQUARED)


def automated_service_spec() -> ServiceSpec:
    """Optimistic: DJI Dock-style automated battery swap."""
    mean = APPROACH_S + UNLOAD_S + AUTOMATED_BATTERY_SWAP_S + LOAD_NEXT_S
    return ServiceSpec(mean_s=mean, cv_squared=AUTOMATED_CV_SQUARED, is_stub=True)
