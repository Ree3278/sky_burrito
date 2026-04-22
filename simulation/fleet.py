"""
Fleet inventory for the simulation's finite-drone model.

This module replaces the "spawn drones from nothing" assumption with a
per-hub pool of idle physical drones plus an origin-side order queue.

Design goals
------------
- Keep the total fleet count exact at all times.
- Seed the initial fleet across active hubs proportionally to hub match_score.
- Let the registry ask simple operational questions:
    * "Does Hub H have an idle drone?"
    * "Check one out from Hub H."
    * "Check one in to Hub H'."
    * "Queue an order at Hub H when no drone is available."
    * "How many queued orders can launch immediately at Hub H?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, List, Mapping

from corridor_pruning.hubs import HUB_LOOKUP
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.allocation import allocate_proportional_integers

if TYPE_CHECKING:
    from hub_sizing.sizing import HubSizingResult

@dataclass(frozen=True)
class FleetSnapshot:
    """Immutable view of the current fleet state for metrics/debugging."""

    idle_by_hub: Dict[int, int]
    queued_orders_by_hub: Dict[int, int]

    @property
    def total_idle(self) -> int:
        return sum(self.idle_by_hub.values())

    @property
    def total_queued_orders(self) -> int:
        return sum(self.queued_orders_by_hub.values())


class FleetPool:
    """
    Manages the finite physical drone fleet across hubs.

    The pool tracks two integers per hub:
    - idle drones currently available to dispatch
    - queued payload orders waiting for an idle drone at that origin hub
    """

    def __init__(
        self,
        initial_idle_by_hub: Mapping[int, int],
        queued_orders_by_hub: Mapping[int, int] | None = None,
    ) -> None:
        if not initial_idle_by_hub:
            raise ValueError("FleetPool requires at least one active hub")

        self._idle_by_hub: Dict[int, int] = {
            int(hub_id): int(count)
            for hub_id, count in initial_idle_by_hub.items()
        }
        self._queued_orders_by_hub: Dict[int, int] = {
            hub_id: 0 for hub_id in self._idle_by_hub
        }

        if queued_orders_by_hub:
            for hub_id, count in queued_orders_by_hub.items():
                self._ensure_hub(hub_id)
                self._queued_orders_by_hub[hub_id] = int(count)

        self._validate_non_negative(self._idle_by_hub, "idle drones")
        self._validate_non_negative(self._queued_orders_by_hub, "queued orders")
        self._total_fleet_size = sum(self._idle_by_hub.values())

    @classmethod
    def from_hub_sizing(
        cls,
        hub_sizing_results: "Iterable[HubSizingResult]",
        total_fleet_size: int = DEFAULT_FLEET_SIZE,
    ) -> "FleetPool":
        """
        Seed a finite fleet across active hubs using sizing-derived demand weights.

        Active hubs are taken from hub sizing results because those are the hubs
        currently in the simulated network. Allocation uses largest-remainder
        rounding so the seeded counts sum exactly to total_fleet_size.
        """
        active_hub_ids = [r.hub_id for r in hub_sizing_results]
        if not active_hub_ids:
            raise ValueError("Cannot seed fleet without active hub sizing results")
        if total_fleet_size <= 0:
            raise ValueError("total_fleet_size must be positive")

        results_by_hub = {result.hub_id: result for result in hub_sizing_results}
        weights = {}
        for hub_id in active_hub_ids:
            result = results_by_hub.get(hub_id)
            if result is None:
                continue
            sizing_weight = max(float(result.offered_load), float(result.lambda_per_hour), 0.0)
            if sizing_weight <= 0 and hub_id in HUB_LOOKUP:
                sizing_weight = float(HUB_LOOKUP[hub_id].match_score)
            weights[hub_id] = sizing_weight

        if len(weights) != len(active_hub_ids):
            missing = sorted(set(active_hub_ids) - set(weights))
            raise KeyError(f"Missing hub metadata for hub ids: {missing}")

        initial_idle_by_hub = allocate_proportional_integers(weights, total_fleet_size)
        return cls(initial_idle_by_hub=initial_idle_by_hub)

    @property
    def total_fleet_size(self) -> int:
        return self._total_fleet_size

    @property
    def active_hub_ids(self) -> List[int]:
        return sorted(self._idle_by_hub)

    def idle_count(self, hub_id: int) -> int:
        self._ensure_hub(hub_id)
        return self._idle_by_hub[hub_id]

    def queued_order_count(self, hub_id: int) -> int:
        self._ensure_hub(hub_id)
        return self._queued_orders_by_hub[hub_id]

    def has_idle_drone(self, hub_id: int) -> bool:
        return self.idle_count(hub_id) > 0

    def checkout_drone(self, hub_id: int) -> bool:
        """
        Reserve one idle drone for a new dispatch from hub_id.

        Returns True on success, False if the hub is empty.
        """
        self._ensure_hub(hub_id)
        if self._idle_by_hub[hub_id] <= 0:
            return False
        self._idle_by_hub[hub_id] -= 1
        return True

    def checkin_drone(self, hub_id: int, count: int = 1) -> None:
        """Return one or more drones to the idle pool at hub_id."""
        self._ensure_hub(hub_id)
        if count < 0:
            raise ValueError("count must be non-negative")
        self._idle_by_hub[hub_id] += count

    def queue_order(self, hub_id: int, count: int = 1) -> None:
        """Add one or more payload orders to the origin queue at hub_id."""
        self._ensure_hub(hub_id)
        if count < 0:
            raise ValueError("count must be non-negative")
        self._queued_orders_by_hub[hub_id] += count

    def pop_queued_orders(self, hub_id: int, count: int = 1) -> int:
        """
        Remove up to `count` queued orders from hub_id and return how many moved.
        """
        self._ensure_hub(hub_id)
        if count < 0:
            raise ValueError("count must be non-negative")
        moved = min(count, self._queued_orders_by_hub[hub_id])
        self._queued_orders_by_hub[hub_id] -= moved
        return moved

    def release_matching_orders(self, hub_id: int) -> int:
        """
        Convert queued demand into immediate launches when drones are available.

        This is useful right after a drone checks in: if the destination hub
        also has waiting demand, the registry can immediately redispatch.

        Returns the number of orders that are now launchable.
        """
        self._ensure_hub(hub_id)
        launches = min(self._idle_by_hub[hub_id], self._queued_orders_by_hub[hub_id])
        self._idle_by_hub[hub_id] -= launches
        self._queued_orders_by_hub[hub_id] -= launches
        return launches

    def reserve_rebalancing_drone(self, origin_hub_id: int) -> bool:
        """
        Reserve one idle drone for a future dead-head dispatch.

        The rebalancing policy should call this when it creates the dead-head
        flight, then call checkin_drone(dest_hub_id) only when that drone
        actually finishes cooldown at the destination.
        """
        return self.checkout_drone(origin_hub_id)

    def idle_by_hub(self) -> Dict[int, int]:
        return dict(self._idle_by_hub)

    def queued_orders_by_hub(self) -> Dict[int, int]:
        return dict(self._queued_orders_by_hub)

    def snapshot(self) -> FleetSnapshot:
        return FleetSnapshot(
            idle_by_hub=self.idle_by_hub(),
            queued_orders_by_hub=self.queued_orders_by_hub(),
        )

    def _ensure_hub(self, hub_id: int) -> None:
        if hub_id not in self._idle_by_hub:
            self._idle_by_hub[hub_id] = 0
            self._queued_orders_by_hub[hub_id] = 0

    @staticmethod
    def _validate_non_negative(values: Mapping[int, int], label: str) -> None:
        bad = {hub_id: count for hub_id, count in values.items() if count < 0}
        if bad:
            raise ValueError(f"{label} cannot be negative: {bad}")
__all__ = [
    "DEFAULT_FLEET_SIZE",
    "FleetPool",
    "FleetSnapshot",
]
