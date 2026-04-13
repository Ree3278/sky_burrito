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
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from corridor_pruning.pruning import ScoredCorridor
    from corridor_pruning.hubs import Hub

# ── Stub parameters ──────────────────────────────────────────────────────────

# Total drones landing across all hubs during the 1-hour peak window.
# Rough basis: 10 active hubs × ~20 orders/hub/hr = 200.
# ⚠ Replace with NHPP simulation output.
NETWORK_PEAK_ORDERS_PER_HOUR: float = 200.0

# Ratio of peak-hour volume to the flat average used above.
# Friday 7–9 PM in SF food delivery is ~2–3× the daily average.
# ⚠ Replace with empirical peak factor from order data.
PEAK_MULTIPLIER: float = 1.0   # already expressed as peak in the constant above


@dataclass
class HubDemand:
    hub_id: int
    flow_weight: float          # relative share of total network traffic
    lambda_per_hour: float      # arrivals/hr  (λ)
    lambda_per_min: float       # arrivals/min (λ/60) — used in M/G/k
    is_stub: bool = True


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
