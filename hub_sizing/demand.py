"""
Stub demand model — peak arrival rate (λ) per hub.

What this replaces
------------------
The real model uses a Non-Homogeneous Poisson Process (NHPP) fit to
historical Friday-night order volumes, giving λ(t) per hub per 15-min
interval. That requires an actual order dataset.

What this stub does
-------------------
1. Assumes a total network peak throughput of NETWORK_PEAK_ORDERS_PER_HOUR
   drones in the air simultaneously during the Friday 7–9 PM window.
2. Distributes λ across the 10 active hubs proportional to each hub's
   "flow weight" — a composite of how much corridor traffic passes through it
   (origin appearances + destination appearances in the shortlist, weighted
   by demand_weight of each corridor).
3. Applies a PEAK_MULTIPLIER to convert from average to peak-hour volume.

Missing inputs
--------------
- Actual order history from a POS or delivery platform
- Time-of-day NHPP fit (λ varies by 15-min bucket, not flat)
- Separate inbound vs outbound rates per hub (currently merged)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, TYPE_CHECKING

from settings.pipeline import NETWORK_PEAK_ORDERS_PER_HOUR, PEAK_MULTIPLIER

if TYPE_CHECKING:
    from corridor_pruning.pruning import ScoredCorridor
    from corridor_pruning.hubs import Hub
    from simulation.environment import HubSetup

# ── Stub parameters ──────────────────────────────────────────────────────────




@dataclass
class HubDemand:
    hub_id: int
    flow_weight: float          # relative share of total network traffic
    lambda_per_hour: float      # arrivals/hr  (λ)
    lambda_per_min: float       # arrivals/min (λ/60) — used in M/G/k
    is_stub: bool = True


def hub_profiles_from_setup_hubs(
    hubs: "Iterable[HubSetup]",
    service_cv_squared: float,
) -> Dict[str, Dict[str, float]]:
    """
    Convert persisted setup hubs into RL-style demand profiles.

    The hub-sizing pipeline already computed λ/hr for each active hub.
    RL uses λ/min as its base demand profile, so we derive it directly here
    instead of maintaining a separate manual table.
    """
    profiles: Dict[str, Dict[str, float]] = {}
    for hub in hubs:
        profiles[f"Hub {hub.hub_id}"] = {
            "lambda_base": hub.lambda_per_hour / 60.0,
            "cv_squared": service_cv_squared,
        }
    return profiles


def estimate_demand(
    shortlist: "List[ScoredCorridor]",
    network_peak: float = NETWORK_PEAK_ORDERS_PER_HOUR,
) -> Dict[int, HubDemand]:
    """
    Compute a stub peak arrival rate for every hub that appears in the shortlist.

    Each corridor contributes its demand_weight once to the origin hub and once
    to the destination hub (a drone lands at both ends).

    Parameters
    ----------
    shortlist : list of ScoredCorridor
    network_peak : float
        Total drones landing across all hubs per peak hour.

    Returns
    -------
    dict mapping hub_id → HubDemand
    """
    flow: Dict[int, float] = {}

    for sc in shortlist:
        oid = sc.corridor.origin.id
        did = sc.corridor.destination.id
        w   = sc.demand_weight

        flow[oid] = flow.get(oid, 0.0) + w
        flow[did] = flow.get(did, 0.0) + w

    total_flow = sum(flow.values())

    demands: Dict[int, HubDemand] = {}
    for hub_id, fw in flow.items():
        lph = (fw / total_flow) * network_peak * PEAK_MULTIPLIER
        demands[hub_id] = HubDemand(
            hub_id          = hub_id,
            flow_weight     = fw / total_flow,
            lambda_per_hour = lph,
            lambda_per_min  = lph / 60.0,
        )

    return demands
