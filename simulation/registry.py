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

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, TYPE_CHECKING

from .drone import Drone, DroneState
from .dispatcher import DispatchRequest, Dispatcher
from .fleet import FleetPool, FleetSnapshot

if TYPE_CHECKING:
    from hub_sizing.sizing import HubSizingResult
    from .rl_bridge import RLBridge

# RL heartbeat: fire once per simulated minute regardless of tick rate.
_RL_HEARTBEAT_S: float = 60.0


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
    fleet: FleetSnapshot
    total_active_drones: int
    total_craning: int
    total_orders_received: int
    total_orders_dispatched: int
    total_craning_events: int
    # RL rebalancing stats (0 when RL is disabled)
    rl_rebalancing_moves:  int = field(default=0)
    rl_drones_rebalanced:  int = field(default=0)


class DroneRegistry:
    """
    Central simulation loop controller.

    Parameters
    ----------
    hub_sizing_results : list of HubSizingResult
        Determines k (pad capacity) per hub.
    dispatcher : Dispatcher
        Generates new payload orders each tick.
    """

    def __init__(
        self,
        hub_sizing_results: "List[HubSizingResult]",
        dispatcher: Dispatcher,
        fleet_pool: FleetPool | None = None,
        rl_bridge: "Optional[RLBridge]" = None,
    ):
        self._hub_sizing_results = list(hub_sizing_results)
        self._drones: Dict[int, Drone] = {}
        self._dispatcher = dispatcher
        self._fleet = fleet_pool or FleetPool.from_hub_sizing(self._hub_sizing_results)
        self._pending_orders_by_hub: Dict[int, Deque[DispatchRequest]] = {
            hub_id: deque() for hub_id in self._fleet.active_hub_ids
        }
        self._hub_metrics: Dict[int, HubMetrics] = {
            r.hub_id: HubMetrics(hub_id=r.hub_id, k_pads=r.k_pads)
            for r in self._hub_sizing_results
        }
        # Default pad count for hubs not in sizing results (Hubs 8, 12)
        self._default_k = 2
        self._total_orders_received = 0
        self._total_orders = 0
        self._total_craning_events = 0

        # ── RL rebalancing bridge ──────────────────────────────────────────
        self._rl_bridge: "Optional[RLBridge]" = rl_bridge
        self._rl_accumulator_s: float = 0.0   # time since last RL heartbeat
        self._rl_total_moves:  int = 0
        self._rl_total_drones: int = 0

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
        new_requests = self._dispatcher.tick(dt_sim_s)
        for request in new_requests:
            self._handle_order_request(request)

        # 1b. RL rebalancing heartbeat — fires every ~60 simulated seconds.
        #     Runs after spawning new orders (so the observation reflects fresh
        #     demand) but before moving drones (so relocated drones can serve
        #     orders this tick).
        rl_moves_this_tick  = 0
        rl_drones_this_tick = 0
        if self._rl_bridge is not None and self._rl_bridge.is_available:
            self._rl_accumulator_s += dt_sim_s
            if self._rl_accumulator_s >= _RL_HEARTBEAT_S:
                self._rl_accumulator_s = 0.0
                sim_hour = self._parse_sim_hour(sim_time_hhmm)
                # Build a lightweight snapshot for the observation (reuse current fleet)
                _obs_snap = _ObsSnapshot(
                    fleet       = self._fleet.snapshot(),
                    hub_metrics = self._hub_metrics,
                )
                result = self._rl_bridge.step(_obs_snap, self._fleet, sim_hour)
                rl_moves_this_tick  = result.drones_relocated  # count moves by drones moved
                rl_drones_this_tick = result.drones_relocated
                self._rl_total_moves  += result.moves_attempted
                self._rl_total_drones += result.drones_relocated

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
        done = [(did, d) for did, d in self._drones.items() if d.done]
        for did, drone in done:
            dest_hub_id = drone.corridor.destination.id
            self._fleet.checkin_drone(dest_hub_id)
            del self._drones[did]
            self._drain_origin_queue(dest_hub_id)

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
            fleet                  = self._fleet.snapshot(),
            total_active_drones    = len(self._drones),
            total_craning          = total_craning,
            total_orders_received  = self._total_orders_received,
            total_orders_dispatched= self._total_orders,
            total_craning_events   = self._total_craning_events,
            rl_rebalancing_moves   = self._rl_total_moves,
            rl_drones_rebalanced   = self._rl_total_drones,
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

    def _handle_order_request(self, request: DispatchRequest) -> None:
        self._total_orders_received += 1

        origin_hub_id = request.origin_hub_id
        if self._pending_orders_by_hub.get(origin_hub_id):
            self._queue_request(request)
            self._drain_origin_queue(origin_hub_id)
            return

        if self._launch_request(request):
            return

        self._queue_request(request)

    def _queue_request(self, request: DispatchRequest) -> None:
        origin_hub_id = request.origin_hub_id
        if origin_hub_id not in self._pending_orders_by_hub:
            self._pending_orders_by_hub[origin_hub_id] = deque()
        self._pending_orders_by_hub[origin_hub_id].append(request)
        self._fleet.queue_order(origin_hub_id)

    def _launch_request(self, request: DispatchRequest) -> bool:
        origin_hub_id = request.origin_hub_id
        if not self._fleet.checkout_drone(origin_hub_id):
            return False

        drone = Drone(
            drone_id=request.request_id,
            corridor=request.corridor,
            cruise_altitude_m=self._dispatcher.cruise_altitude_m,
        )
        self._drones[drone.drone_id] = drone
        self._total_orders += 1
        return True

    def _drain_origin_queue(self, hub_id: int) -> None:
        pending = self._pending_orders_by_hub.get(hub_id)
        if not pending:
            return

        while pending and self._fleet.has_idle_drone(hub_id):
            request = pending[0]
            launched = self._launch_request(request)
            if not launched:
                break
            pending.popleft()
            self._fleet.pop_queued_orders(hub_id)

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
        self._fleet = FleetPool.from_hub_sizing(
            self._hub_sizing_results,
            total_fleet_size=self._fleet.total_fleet_size,
        )
        self._pending_orders_by_hub = {
            hub_id: deque() for hub_id in self._fleet.active_hub_ids
        }
        for m in self._hub_metrics.values():
            m.pads_in_use = 0
            m.drones_craning = 0
            m.total_landings = 0
            m.total_craning_events = 0
        self._total_orders_received = 0
        self._total_orders = 0
        self._total_craning_events = 0
        self._rl_accumulator_s = 0.0
        self._rl_total_moves   = 0
        self._rl_total_drones  = 0
        if self._rl_bridge is not None:
            self._rl_bridge.reset_episode()

    @staticmethod
    def _parse_sim_hour(hhmm: str) -> float:
        """Convert '18:42' → 18.7."""
        try:
            h, m = hhmm.split(":")
            return int(h) + int(m) / 60.0
        except (ValueError, AttributeError):
            return 0.0


# ---------------------------------------------------------------------------
# Lightweight snapshot proxy used for RL observation building.
# Avoids building a full SimSnapshot just for the RL step.
# ---------------------------------------------------------------------------

@dataclass
class _ObsSnapshot:
    """Minimal snapshot passed to RLBridge.step() at each heartbeat."""
    fleet: FleetSnapshot
    hub_metrics: Dict[int, "HubMetrics"]
