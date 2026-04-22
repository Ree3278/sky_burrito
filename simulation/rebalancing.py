"""
Rebalancing policy for the finite-drone simulation.

Goal
----
Keep a per-hub "target idle inventory" (how many drones we'd like sitting
available at each hub) based on a demand-weight distribution, then
deadhead (reposition) idle drones from surplus hubs to deficit hubs.

This is intentionally simple and deterministic:
- We only move *idle* drones (never interrupt an active payload flight).
- We account for queued orders by treating them as additional immediate need.
- We move at most N drones per tick to avoid thrashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

from simulation.allocation import allocate_proportional_integers


def allocate_targets_from_weights(
    weights: Mapping[int, float],
    total_units: int,
    *,
    min_per_hub: int = 0,
) -> Dict[int, int]:
    """
    Allocate an exact integer total across hubs, proportional to weights.

    Uses largest-remainder rounding after first assigning min_per_hub to each hub.
    """
    return allocate_proportional_integers(
        weights,
        total_units,
        min_per_key=min_per_hub,
    )


@dataclass(frozen=True)
class RebalanceMove:
    origin_hub_id: int
    dest_hub_id: int


class DemandRebalancer:
    """
    Very small "inventory balancing" rebalancer.

    The intended interpretation of target_idle_by_hub is:
      target_idle = how many drones we'd like AVAILABLE at that hub.

    We also treat queued orders as extra immediate need, i.e. a hub with a big
    queue should pull drones in even if it is already at its target idle.
    """

    def __init__(
        self,
        target_idle_by_hub: Mapping[int, int],
        *,
        enabled: bool = True,
        max_moves_per_tick: int = 1,
    ) -> None:
        self._target: Dict[int, int] = {int(k): int(v) for k, v in target_idle_by_hub.items()}
        self.enabled = bool(enabled)
        self.max_moves_per_tick = int(max_moves_per_tick)
        if self.max_moves_per_tick < 0:
            raise ValueError("max_moves_per_tick must be non-negative")

    @property
    def target_idle_by_hub(self) -> Dict[int, int]:
        return dict(self._target)

    def propose_moves(
        self,
        *,
        idle_by_hub: Mapping[int, int],
        queued_orders_by_hub: Mapping[int, int],
    ) -> List[RebalanceMove]:
        if not self.enabled or self.max_moves_per_tick == 0:
            return []

        hub_ids = sorted(set(self._target) | set(idle_by_hub) | set(queued_orders_by_hub))

        # need(h) > 0 means "we want more drones here"
        need: Dict[int, int] = {}
        for hid in hub_ids:
            target = int(self._target.get(hid, 0))
            idle = int(idle_by_hub.get(hid, 0))
            queued = int(queued_orders_by_hub.get(hid, 0))
            need[hid] = (target + queued) - idle

        donors = [hid for hid in hub_ids if need[hid] < 0 and int(idle_by_hub.get(hid, 0)) > 0]
        receivers = [hid for hid in hub_ids if need[hid] > 0]

        # Biggest shortages first, biggest surpluses first.
        donors.sort(key=lambda hid: (need[hid], int(idle_by_hub.get(hid, 0)), -hid))  # most negative need first
        receivers.sort(key=lambda hid: (need[hid], -hid), reverse=True)

        moves: List[RebalanceMove] = []
        donor_idx = 0

        for recv in receivers:
            while donor_idx < len(donors) and need[recv] > 0 and len(moves) < self.max_moves_per_tick:
                donor = donors[donor_idx]
                if donor == recv:
                    donor_idx += 1
                    continue

                # One drone move reduces receiver need by 1 and increases donor need by 1.
                moves.append(RebalanceMove(origin_hub_id=donor, dest_hub_id=recv))
                need[recv] -= 1
                need[donor] += 1

                # Donor no longer has surplus
                if need[donor] >= 0:
                    donor_idx += 1

            if len(moves) >= self.max_moves_per_tick:
                break

        return moves


__all__ = [
    "allocate_targets_from_weights",
    "DemandRebalancer",
    "RebalanceMove",
]
