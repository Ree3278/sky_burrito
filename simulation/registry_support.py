"""Internal helpers for registry routing and pad-accounting logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Optional

from simulation.drone import Drone, DroneState

if TYPE_CHECKING:
    from corridor_pruning.corridors import Corridor
    from corridor_pruning.pruning import ScoredCorridor
    from simulation.dispatcher import DispatchRequest
    from simulation.fleet import FleetPool
    from simulation.registry import HubMetrics


def choose_cross_hub_corridor(
    request: "DispatchRequest",
    shortlist: Iterable["ScoredCorridor"],
    fleet: "FleetPool",
) -> Optional["Corridor"]:
    """Pick the nearest alternative origin that can serve the same destination."""
    dest_hub_id = request.destination_hub_id
    best_corridor = None
    best_distance_m = float("inf")

    for scored in shortlist:
        corridor = scored.corridor
        if (
            corridor.destination.id == dest_hub_id
            and corridor.origin.id != request.origin_hub_id
            and fleet.has_idle_drone(corridor.origin.id)
            and corridor.straight_line_m < best_distance_m
        ):
            best_distance_m = corridor.straight_line_m
            best_corridor = corridor

    return best_corridor


def recount_hub_metrics(
    drones: Iterable[Drone],
    hub_metrics: Dict[int, "HubMetrics"],
    get_hub_metrics,
) -> None:
    """Recompute pad occupancy and craning counts from the active drone set."""
    for metrics in hub_metrics.values():
        metrics.pads_in_use = 0
        metrics.drones_craning = 0

    for drone in drones:
        destination_id = drone.corridor.destination.id
        metrics = get_hub_metrics(destination_id)
        if drone.state in (DroneState.LANDING, DroneState.COOLDOWN):
            metrics.pads_in_use += 1
            if drone.state == DroneState.COOLDOWN:
                metrics.total_landings += 1
        elif drone.state == DroneState.CRANING:
            metrics.drones_craning += 1


def pad_is_free(
    hub_id: int,
    drones: Iterable[Drone],
    hub_metrics: Dict[int, "HubMetrics"],
    exclude_drone_id: int,
    get_hub_metrics,
) -> bool:
    """Return True if at least one pad is free for the destination hub."""
    metrics = hub_metrics.get(hub_id) or get_hub_metrics(hub_id)
    occupied = sum(
        1
        for drone in drones
        if drone.drone_id != exclude_drone_id
        and drone.state in (DroneState.LANDING, DroneState.COOLDOWN)
        and drone.corridor.destination.id == hub_id
    )
    return occupied < metrics.k_pads


__all__ = ["choose_cross_hub_corridor", "pad_is_free", "recount_hub_metrics"]
