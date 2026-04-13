"""
Drone registry — the single source of truth for the live simulation state.

Responsibilities
----------------
- Hold every active Drone object
- Track pad occupancy per hub (drones in COOLDOWN or LANDING at that hub)
- Detect and record craning events
- Advance all drones on each tick
- Emit per-tick snapshot dicts for Pydeck rendering
- Collect running metrics (total orders, craning events, busiest hub)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

from .drone import Drone, DroneState
from .dispatcher import Dispatcher

if TYPE_CHECKING:
    from hub_sizing.sizing import HubSizingResult


@dataclass
class HubMetrics:
    hub_id: int
    k_pads: int
    pads_in_use: int = 0
    drones_craning: int = 0
    total_landings: int = 0
    total_craning_events: int = 0

    @property
    def utilisation_pct(self) -> float:
        if self.k_pads == 0:
            return 0.0
        return min(100.0, self.pads_in_use / self.k_pads * 100)

    @property
    def is_saturated(self) -> bool:
        return self.pads_in_use >= self.k_pads


@dataclass
class SimSnapshot:
    """Everything the Pydeck app needs for a single frame."""
    sim_time_hhmm: str
    drones: List[dict]                    # each drone's to_dict()
    hub_metrics: Dict[int, HubMetrics]
    total_active_drones: int
    total_craning: int
    total_orders_dispatched: int
    total_craning_events: int


class DroneRegistry:
    """
    Central simulation loop controller.

    Parameters
    ----------
    hub_sizing_results : list of HubSizingResult
        Determines k (pad capacity) per hub.
    dispatcher : Dispatcher
        Spawns new drones each tick.
    """

    def __init__(
        self,
        hub_sizing_results: "List[HubSizingResult]",
        dispatcher: Dispatcher,
    ):
        self._drones: Dict[int, Drone] = {}
        self._dispatcher = dispatcher
        self._hub_metrics: Dict[int, HubMetrics] = {
            r.hub_id: HubMetrics(hub_id=r.hub_id, k_pads=r.k_pads)
            for r in hub_sizing_results
        }
        # Default pad count for hubs not in sizing results (Hubs 8, 12)
        self._default_k = 2
        self._total_orders = 0
        self._total_craning_events = 0

    # ── Tick ─────────────────────────────────────────────────────────────────

    def tick(self, dt_sim_s: float, sim_time_hhmm: str) -> SimSnapshot:
        """
        Advance the full simulation by dt_sim_s seconds.

        1. Spawn new drones from dispatcher
        2. Move all existing drones
        3. Retire drones that have completed their journey
        4. Recount pad occupancy
        5. Return snapshot
        """
        # 1. Spawn
        new_drones = self._dispatcher.tick(dt_sim_s)
        for d in new_drones:
            self._drones[d.drone_id] = d
            self._total_orders += 1

        # 2. Move
        self._recount_pads()   # refresh before checking pad availability
        for drone in list(self._drones.values()):
            dest_id = drone.corridor.destination.id
            pad_free = self._pad_free(dest_id, exclude_drone=drone)
            prev_state = drone.state
            drone.move(dt_sim_s, pad_free_at_dest=pad_free)

            # Track craning events (new transitions INTO craning)
            if drone.state == DroneState.CRANING and prev_state != DroneState.CRANING:
                self._total_craning_events += 1
                m = self._get_hub_metrics(dest_id)
                m.total_craning_events += 1

        # 3. Retire completed drones
        done = [did for did, d in self._drones.items() if d.done]
        for did in done:
            del self._drones[did]

        # 4. Final recount
        self._recount_pads()

        # 5. Snapshot
        total_craning = sum(
            1 for d in self._drones.values() if d.state == DroneState.CRANING
        )

        return SimSnapshot(
            sim_time_hhmm          = sim_time_hhmm,
            drones                 = [d.to_dict() for d in self._drones.values()],
            hub_metrics            = dict(self._hub_metrics),
            total_active_drones    = len(self._drones),
            total_craning          = total_craning,
            total_orders_dispatched= self._total_orders,
            total_craning_events   = self._total_craning_events,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _recount_pads(self) -> None:
        """Reset and recount pad usage from current drone states."""
        for m in self._hub_metrics.values():
            m.pads_in_use = 0
            m.drones_craning = 0

        for drone in self._drones.values():
            if drone.state in (DroneState.LANDING, DroneState.COOLDOWN):
                m = self._get_hub_metrics(drone.corridor.destination.id)
                m.pads_in_use += 1
                m.total_landings += 1 if drone.state == DroneState.COOLDOWN else 0
            elif drone.state == DroneState.CRANING:
                m = self._get_hub_metrics(drone.corridor.destination.id)
                m.drones_craning += 1

    def _pad_free(self, hub_id: int, exclude_drone: Drone) -> bool:
        """True if the hub has at least one pad not occupied by a different drone."""
        m = self._get_hub_metrics(hub_id)
        occupied = sum(
            1 for d in self._drones.values()
            if d.drone_id != exclude_drone.drone_id
            and d.state in (DroneState.LANDING, DroneState.COOLDOWN)
            and d.corridor.destination.id == hub_id
        )
        return occupied < m.k_pads

    def _get_hub_metrics(self, hub_id: int) -> HubMetrics:
        if hub_id not in self._hub_metrics:
            self._hub_metrics[hub_id] = HubMetrics(
                hub_id=hub_id, k_pads=self._default_k
            )
        return self._hub_metrics[hub_id]

    def reset(self) -> None:
        self._drones.clear()
        for m in self._hub_metrics.values():
            m.pads_in_use = 0
            m.drones_craning = 0
            m.total_landings = 0
            m.total_craning_events = 0
        self._total_orders = 0
        self._total_craning_events = 0
