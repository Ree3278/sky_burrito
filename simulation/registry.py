"""Central simulation loop and state snapshotting for the live app."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque, Dict, List, Optional

from simulation.registry_support import (
    choose_cross_hub_corridor,
    pad_is_free,
    recount_hub_metrics,
)
from simulation.rl_schema import RL_HEARTBEAT_S

from .dispatcher import Dispatcher, DispatchRequest
from .drone import Drone, DroneState
from .fleet import FleetPool, FleetSnapshot

if TYPE_CHECKING:
    from hub_sizing.sizing import HubSizingResult

    from .rl_bridge import RLBridge


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
    drones: List[dict]
    hub_metrics: Dict[int, HubMetrics]
    fleet: FleetSnapshot
    total_active_drones: int
    total_craning: int
    total_orders_received: int
    total_orders_dispatched: int
    total_craning_events: int
    rl_rebalancing_moves: int = field(default=0)
    rl_drones_rebalanced: int = field(default=0)


@dataclass
class _ObsSnapshot:
    """Minimal snapshot shape consumed by the RL bridge."""

    fleet: FleetSnapshot
    hub_metrics: Dict[int, HubMetrics]


class DroneRegistry:
    """Main runtime coordinator for payload creation, movement, and metrics."""

    def __init__(
        self,
        hub_sizing_results: "List[HubSizingResult]",
        dispatcher: Dispatcher,
        fleet_pool: FleetPool | None = None,
        rl_bridge: "Optional[RLBridge]" = None,
    ):
        self._hub_sizing_results = list(hub_sizing_results)
        self._dispatcher = dispatcher
        self._fleet = fleet_pool or FleetPool.from_hub_sizing(self._hub_sizing_results)
        self._rl_bridge = rl_bridge

        self._drones: Dict[int, Drone] = {}
        self._pending_orders_by_hub: Dict[int, Deque[DispatchRequest]] = {
            hub_id: deque() for hub_id in self._fleet.active_hub_ids
        }
        self._hub_metrics: Dict[int, HubMetrics] = {
            result.hub_id: HubMetrics(hub_id=result.hub_id, k_pads=result.k_pads)
            for result in self._hub_sizing_results
        }
        self._default_k = 2
        self._rl_accumulator_s = 0.0
        self._rl_total_moves = 0
        self._rl_total_drones = 0
        self._total_orders_received = 0
        self._total_orders = 0
        self._total_craning_events = 0

    def tick(self, dt_sim_s: float, sim_time_hhmm: str) -> SimSnapshot:
        """Advance the live simulation state and return the new snapshot."""
        sim_hour = self._parse_sim_hour(sim_time_hhmm)
        self._spawn_new_requests(dt_sim_s, sim_hour)
        self._run_rl_if_due(dt_sim_s, sim_hour)
        self._advance_drones(dt_sim_s)
        self._retire_completed_drones()
        self._recount_pads()
        return self._snapshot(sim_time_hhmm)

    def reset(self) -> None:
        """Reset the registry back to its initial empty-flight state."""
        self._drones.clear()
        self._fleet = FleetPool.from_hub_sizing(
            self._hub_sizing_results,
            total_fleet_size=self._fleet.total_fleet_size,
        )
        self._pending_orders_by_hub = {
            hub_id: deque() for hub_id in self._fleet.active_hub_ids
        }
        for metrics in self._hub_metrics.values():
            metrics.pads_in_use = 0
            metrics.drones_craning = 0
            metrics.total_landings = 0
            metrics.total_craning_events = 0
        self._rl_accumulator_s = 0.0
        self._rl_total_moves = 0
        self._rl_total_drones = 0
        self._total_orders_received = 0
        self._total_orders = 0
        self._total_craning_events = 0
        if self._rl_bridge is not None:
            self._rl_bridge.reset_episode()

    def _spawn_new_requests(self, dt_sim_s: float, sim_hour: float) -> None:
        for request in self._dispatcher.tick(dt_sim_s, sim_hour):
            self._handle_order_request(request)

    def _run_rl_if_due(self, dt_sim_s: float, sim_hour: float) -> None:
        if self._rl_bridge is None or not self._rl_bridge.is_available:
            return
        self._rl_accumulator_s += dt_sim_s
        if self._rl_accumulator_s < RL_HEARTBEAT_S:
            return

        self._rl_accumulator_s = 0.0
        snapshot = _ObsSnapshot(
            fleet=self._fleet.snapshot(),
            hub_metrics=self._hub_metrics,
        )
        result = self._rl_bridge.step(snapshot, self._fleet, sim_hour)
        self._rl_total_moves += result.moves_attempted
        self._rl_total_drones += result.drones_relocated

    def _advance_drones(self, dt_sim_s: float) -> None:
        self._recount_pads()
        for drone in list(self._drones.values()):
            destination_id = drone.corridor.destination.id
            pad_free = self._pad_free(destination_id, drone)
            previous_state = drone.state
            drone.move(dt_sim_s, pad_free_at_dest=pad_free)
            if drone.state == DroneState.CRANING and previous_state != DroneState.CRANING:
                self._total_craning_events += 1
                self._get_hub_metrics(destination_id).total_craning_events += 1

    def _retire_completed_drones(self) -> None:
        completed = [(drone_id, drone) for drone_id, drone in self._drones.items() if drone.done]
        for drone_id, drone in completed:
            destination_hub_id = drone.corridor.destination.id
            self._fleet.checkin_drone(destination_hub_id)
            del self._drones[drone_id]
            self._drain_origin_queue(destination_hub_id)

    def _snapshot(self, sim_time_hhmm: str) -> SimSnapshot:
        total_craning = sum(
            1 for drone in self._drones.values() if drone.state == DroneState.CRANING
        )
        return SimSnapshot(
            sim_time_hhmm=sim_time_hhmm,
            drones=[drone.to_dict() for drone in self._drones.values()],
            hub_metrics=dict(self._hub_metrics),
            fleet=self._fleet.snapshot(),
            total_active_drones=len(self._drones),
            total_craning=total_craning,
            total_orders_received=self._total_orders_received,
            total_orders_dispatched=self._total_orders,
            total_craning_events=self._total_craning_events,
            rl_rebalancing_moves=self._rl_total_moves,
            rl_drones_rebalanced=self._rl_total_drones,
        )

    def _recount_pads(self) -> None:
        recount_hub_metrics(
            self._drones.values(),
            self._hub_metrics,
            self._get_hub_metrics,
        )

    def _handle_order_request(self, request: DispatchRequest) -> None:
        self._total_orders_received += 1
        origin_hub_id = request.origin_hub_id

        if self._pending_orders_by_hub.get(origin_hub_id):
            self._queue_request(request)
            self._drain_origin_queue(origin_hub_id)
            return

        if self._launch_request(request):
            return

        alternative_corridor = choose_cross_hub_corridor(
            request,
            self._dispatcher.shortlist,
            self._fleet,
        )
        if alternative_corridor is not None:
            alternative_request = DispatchRequest(
                request_id=request.request_id,
                corridor=alternative_corridor,
            )
            if self._launch_request(alternative_request):
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
            if not self._launch_request(request):
                break
            pending.popleft()
            self._fleet.pop_queued_orders(hub_id)

    def _pad_free(self, hub_id: int, drone: Drone) -> bool:
        return pad_is_free(
            hub_id,
            self._drones.values(),
            self._hub_metrics,
            drone.drone_id,
            self._get_hub_metrics,
        )

    def _get_hub_metrics(self, hub_id: int) -> HubMetrics:
        if hub_id not in self._hub_metrics:
            self._hub_metrics[hub_id] = HubMetrics(hub_id=hub_id, k_pads=self._default_k)
        return self._hub_metrics[hub_id]

    @staticmethod
    def _parse_sim_hour(hhmm: str) -> float:
        try:
            hour, minute = hhmm.split(":")
            return int(hour) + int(minute) / 60.0
        except (AttributeError, ValueError):
            return 0.0


__all__ = ["DroneRegistry", "HubMetrics", "SimSnapshot"]
