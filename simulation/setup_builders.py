"""Builders and converters for simulation setup and runtime environments."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Dict, List

from corridor_pruning.corridors import Corridor
from corridor_pruning.hubs import HUB_LOOKUP, Hub
from corridor_pruning.pruning import ScoredCorridor, prune_corridors
from hub_sizing.service import ServiceSpec, automated_service_spec, default_service_spec
from hub_sizing.sizing import HubSizingResult, size_hubs
from settings.rl import ACTIVE_HUBS as RL_ACTIVE_HUBS
from simulation.dispatcher import Dispatcher
from simulation.fleet import FleetPool
from simulation.registry import DroneRegistry

from .setup_models import (
    HubSetup,
    RouteSetup,
    SimulationEnvironment,
    SimulationEnvironmentConfig,
    SimulationRuntimeConfig,
    SimulationSetup,
    SimulationSetupConfig,
)

if TYPE_CHECKING:
    from simulation.rl_bridge import RLBridge


def build_simulation_setup(
    config: SimulationSetupConfig | None = None,
) -> SimulationSetup:
    """Build the persisted setup artifact from the corridor shortlist and hub sizing."""
    config = config or SimulationSetupConfig()
    service_spec = _service_spec_from_config(config)

    routes = prune_corridors(
        top_n=config.route_count,
        sim_hour=config.sim_hour,
        buildings_csv=config.buildings_csv,
    )
    allowed_hub_names = set(config.allowed_hub_names or RL_ACTIVE_HUBS)
    filtered_routes = [
        route
        for route in routes
        if f"Hub {route.corridor.origin.id}" in allowed_hub_names
        and f"Hub {route.corridor.destination.id}" in allowed_hub_names
    ][: config.route_count]
    sizing_results = size_hubs(filtered_routes, service_spec=service_spec)

    network_peak_orders_per_hour = sum(result.lambda_per_hour for result in sizing_results)
    hub_lookup = {
        result.hub_id: _hub_setup_from_result(result)
        for result in sizing_results
    }

    return SimulationSetup(
        config=config,
        service_mean_s=service_spec.mean_s,
        service_cv_squared=service_spec.cv_squared,
        network_peak_orders_per_hour=network_peak_orders_per_hour,
        routes=[_route_setup_from_scored(route) for route in filtered_routes],
        hubs=[hub_lookup[hub_id] for hub_id in sorted(hub_lookup)],
    )


def build_runtime_environment(
    setup: SimulationSetup,
    runtime_config: SimulationRuntimeConfig | None = None,
) -> SimulationEnvironment:
    """Convert a persisted setup into live runtime objects."""
    runtime_config = runtime_config or SimulationRuntimeConfig()
    hubs_lookup = {
        hub.hub_id: Hub(
            id=hub.hub_id,
            lat=hub.lat,
            lon=hub.lon,
            restaurants_nearby=hub.restaurants_nearby,
            resunits_nearby=hub.resunits_nearby,
        )
        for hub in setup.hubs
    }
    service_spec = ServiceSpec(
        mean_s=setup.service_mean_s,
        cv_squared=setup.service_cv_squared,
        is_stub=True,
    )
    routes = [_route_setup_to_scored(route, hubs_lookup) for route in setup.routes]
    sizing_results = [
        _hub_setup_to_sizing_result(hub, service_spec)
        for hub in setup.hubs
    ]
    sizing_results = _apply_pad_override(sizing_results, runtime_config.pad_override)

    return SimulationEnvironment(
        setup=setup,
        runtime_config=runtime_config,
        routes=routes,
        sizing_results=sizing_results,
        hubs_lookup=hubs_lookup,
    )


def build_simulation_environment(
    config: SimulationEnvironmentConfig | None = None,
) -> SimulationEnvironment:
    """Build the full runtime environment directly from a high-level config."""
    config = config or SimulationEnvironmentConfig()
    setup = build_simulation_setup(config.setup_config())
    return build_runtime_environment(setup, config.runtime_config())


def create_registry(
    environment: SimulationEnvironment,
    rl_bridge: "RLBridge | None" = None,
) -> DroneRegistry:
    """Create the live registry, dispatcher, and finite fleet from an environment."""
    dispatcher = Dispatcher(
        shortlist=environment.routes,
        lambda_per_sim_s=environment.lambda_per_sim_s,
    )
    fleet_pool = FleetPool.from_hub_sizing(
        environment.sizing_results,
        total_fleet_size=environment.runtime_config.fleet_size,
    )
    return DroneRegistry(
        hub_sizing_results=environment.sizing_results,
        dispatcher=dispatcher,
        fleet_pool=fleet_pool,
        rl_bridge=rl_bridge,
    )


def _service_spec_from_config(config: SimulationSetupConfig) -> ServiceSpec:
    return automated_service_spec() if config.use_automated_swap else default_service_spec()


def _route_setup_from_scored(scored: ScoredCorridor) -> RouteSetup:
    corridor = scored.corridor
    return RouteSetup(
        origin_id=corridor.origin.id,
        destination_id=corridor.destination.id,
        straight_line_m=corridor.straight_line_m,
        bearing_deg=corridor.bearing_deg,
        obstacle_height_m=corridor.obstacle_height_m,
        drone_time_s=scored.drone_time_s,
        ground_time_s=scored.ground_time_s,
        time_delta_s=scored.time_delta_s,
        road_distance_m=corridor.road_distance_m or 0.0,
        detour_ratio=corridor.detour_ratio or 0.0,
        drone_energy_wh=scored.drone_energy_wh,
        ground_energy_wh=scored.ground_energy_wh,
        energy_ratio=scored.energy_ratio,
        demand_weight=scored.demand_weight,
        ground_cost_usd=scored.ground_cost_usd,
        drone_cost_usd=scored.drone_cost_usd,
        cost_arbitrage_usd=scored.cost_arbitrage_usd,
        cost_ratio=scored.cost_ratio,
        uber_payout_breakdown=dict(scored.uber_payout_breakdown),
        drone_co2_g=scored.drone_co2_g,
        ground_co2_g=scored.ground_co2_g,
        co2_saved_g=scored.co2_saved_g,
        co2_reduction_pct=scored.co2_reduction_pct,
        composite_score=scored.composite_score,
        used_stubs=scored.used_stubs,
    )


def _route_setup_to_scored(
    route: RouteSetup,
    hubs_lookup: Dict[int, Hub],
) -> ScoredCorridor:
    corridor = Corridor(
        origin=hubs_lookup[route.origin_id],
        destination=hubs_lookup[route.destination_id],
    )
    corridor.obstacle_height_m = route.obstacle_height_m
    corridor.drone_time_s = route.drone_time_s
    corridor.ground_time_s = route.ground_time_s
    corridor.road_distance_m = route.road_distance_m
    corridor.detour_ratio = route.detour_ratio
    corridor.time_delta_s = route.time_delta_s

    return ScoredCorridor(
        corridor=corridor,
        drone_time_s=route.drone_time_s,
        ground_time_s=route.ground_time_s,
        time_delta_s=route.time_delta_s,
        drone_energy_wh=route.drone_energy_wh,
        ground_energy_wh=route.ground_energy_wh,
        energy_ratio=route.energy_ratio,
        demand_weight=route.demand_weight,
        ground_cost_usd=route.ground_cost_usd,
        drone_cost_usd=route.drone_cost_usd,
        cost_arbitrage_usd=route.cost_arbitrage_usd,
        cost_ratio=route.cost_ratio,
        uber_payout_breakdown=dict(route.uber_payout_breakdown),
        drone_co2_g=route.drone_co2_g,
        ground_co2_g=route.ground_co2_g,
        co2_saved_g=route.co2_saved_g,
        co2_reduction_pct=route.co2_reduction_pct,
        composite_score=route.composite_score,
        used_stubs=route.used_stubs,
    )


def _hub_setup_from_result(result: HubSizingResult) -> HubSetup:
    hub = HUB_LOOKUP[result.hub_id]
    return HubSetup(
        hub_id=result.hub_id,
        lat=hub.lat,
        lon=hub.lon,
        restaurants_nearby=hub.restaurants_nearby,
        resunits_nearby=hub.resunits_nearby,
        lambda_per_hour=result.lambda_per_hour,
        offered_load=result.offered_load,
        k_pads=result.k_pads,
        k_bays=result.k_bays,
        utilisation_pct=result.utilisation_pct,
        p_cran_pct=result.p_cran_pct,
        p_cran_minus1_pct=result.p_cran_minus1_pct,
        tier=result.tier,
        binding_constraint=result.binding_constraint,
        is_stub=result.is_stub,
    )


def _hub_setup_to_sizing_result(
    hub: HubSetup,
    service_spec: ServiceSpec,
) -> HubSizingResult:
    return HubSizingResult(
        hub_id=hub.hub_id,
        lambda_per_hour=hub.lambda_per_hour,
        offered_load=hub.offered_load,
        k_pads=hub.k_pads,
        k_bays=hub.k_bays,
        utilisation_pct=hub.utilisation_pct,
        p_cran_pct=hub.p_cran_pct,
        p_cran_minus1_pct=hub.p_cran_minus1_pct,
        tier=hub.tier,
        binding_constraint=hub.binding_constraint,
        service_spec=service_spec,
        is_stub=hub.is_stub,
    )


def _apply_pad_override(
    sizing_results: List[HubSizingResult],
    pad_override: int,
) -> List[HubSizingResult]:
    if pad_override <= 0:
        return sizing_results

    return [
        replace(result, k_pads=pad_override, k_bays=pad_override)
        for result in sizing_results
    ]


__all__ = [
    "build_runtime_environment",
    "build_simulation_environment",
    "build_simulation_setup",
    "create_registry",
]
