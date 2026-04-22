"""Focused tests for registry routing, queueing, and drain behavior."""

from __future__ import annotations

from corridor_pruning.corridors import Corridor
from corridor_pruning.hubs import HUB_LOOKUP
from corridor_pruning.pruning import ScoredCorridor
from hub_sizing.service import default_service_spec
from hub_sizing.sizing import HubSizingResult
from simulation.dispatcher import Dispatcher, DispatchRequest
from simulation.drone import DroneState
from simulation.fleet import FleetPool
from simulation.registry import DroneRegistry


def make_scored_corridor(origin_id: int, destination_id: int) -> ScoredCorridor:
    corridor = Corridor(HUB_LOOKUP[origin_id], HUB_LOOKUP[destination_id])
    corridor.drone_time_s = 120.0
    corridor.ground_time_s = 240.0
    corridor.time_delta_s = 120.0
    corridor.road_distance_m = corridor.straight_line_m * 1.2
    corridor.detour_ratio = 1.2
    return ScoredCorridor(
        corridor=corridor,
        drone_time_s=120.0,
        ground_time_s=240.0,
        time_delta_s=120.0,
        drone_energy_wh=10.0,
        ground_energy_wh=20.0,
        energy_ratio=2.0,
        demand_weight=corridor.demand_weight,
        ground_cost_usd=8.0,
        drone_cost_usd=2.0,
        cost_arbitrage_usd=6.0,
        cost_ratio=4.0,
        uber_payout_breakdown={},
        drone_co2_g=10.0,
        ground_co2_g=100.0,
        co2_saved_g=90.0,
        co2_reduction_pct=90.0,
        composite_score=100.0,
        used_stubs=True,
    )


def make_hub_result(hub_id: int) -> HubSizingResult:
    return HubSizingResult(
        hub_id=hub_id,
        lambda_per_hour=10.0,
        offered_load=1.0,
        k_pads=2,
        k_bays=2,
        utilisation_pct=50.0,
        p_cran_pct=5.0,
        p_cran_minus1_pct=20.0,
        tier="LIGHT",
        binding_constraint="utilisation",
        service_spec=default_service_spec(),
        is_stub=True,
    )


def test_registry_uses_cross_hub_fallback_when_origin_is_empty():
    primary = make_scored_corridor(1, 6)
    alternative = make_scored_corridor(2, 6)
    registry = DroneRegistry(
        hub_sizing_results=[make_hub_result(1), make_hub_result(2), make_hub_result(6)],
        dispatcher=Dispatcher([primary, alternative], lambda_per_sim_s=0.0),
        fleet_pool=FleetPool({1: 0, 2: 1, 6: 0}),
    )

    registry._handle_order_request(DispatchRequest(request_id=1, corridor=primary.corridor))

    assert len(registry._drones) == 1
    launched = next(iter(registry._drones.values()))
    assert launched.corridor.origin.id == 2
    assert registry._fleet.queued_order_count(1) == 0


def test_registry_checkin_immediately_drains_destination_queue():
    outbound = make_scored_corridor(1, 6)
    return_leg = make_scored_corridor(6, 1)
    registry = DroneRegistry(
        hub_sizing_results=[make_hub_result(1), make_hub_result(6)],
        dispatcher=Dispatcher([outbound, return_leg], lambda_per_sim_s=0.0),
        fleet_pool=FleetPool({1: 1, 6: 0}),
    )

    registry._handle_order_request(DispatchRequest(request_id=1, corridor=outbound.corridor))
    registry._handle_order_request(DispatchRequest(request_id=2, corridor=return_leg.corridor))

    assert registry._fleet.queued_order_count(6) == 1
    active = next(iter(registry._drones.values()))
    active.state = DroneState.IDLE
    active.cooldown_remaining_s = 0.0

    registry._retire_completed_drones()

    assert registry._fleet.queued_order_count(6) == 0
    assert len(registry._drones) == 1
    relaunched = next(iter(registry._drones.values()))
    assert relaunched.corridor.origin.id == 6
    assert relaunched.corridor.destination.id == 1
