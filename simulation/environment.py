"""Shared environment setup for the live simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, TYPE_CHECKING

from corridor_pruning.hubs import HUB_LOOKUP, Hub
from corridor_pruning.pruning import ScoredCorridor, prune_corridors
from hub_sizing.service import automated_service_spec, default_service_spec
from hub_sizing.sizing import HubSizingResult, size_hubs
from settings.paths import BUILDINGS_CSV
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
)
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.dispatcher import Dispatcher
from simulation.fleet import FleetPool
from simulation.registry import DroneRegistry

if TYPE_CHECKING:
    from hub_sizing.service import ServiceSpec
    from simulation.rl_bridge import RLBridge


@dataclass(frozen=True)
class SimulationEnvironmentConfig:
    route_count: int = DEFAULT_SIMULATION_CORRIDOR_COUNT
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR
    demand_scale: float = DEFAULT_DEMAND_SCALE
    use_automated_swap: bool = False
    pad_override: int = 0
    fleet_size: int = DEFAULT_FLEET_SIZE
    buildings_csv: Optional[str] = str(BUILDINGS_CSV)


@dataclass(frozen=True)
class SimulationEnvironment:
    config: SimulationEnvironmentConfig
    routes: List[ScoredCorridor]
    sizing_results: List[HubSizingResult]
    hubs_lookup: Dict[int, Hub]
    service_spec: "ServiceSpec"
    network_peak_orders_per_hour: float

    @property
    def active_hub_ids(self) -> List[int]:
        return sorted(self.hubs_lookup)

    @property
    def lambda_per_sim_s(self) -> float:
        return self.network_peak_orders_per_hour / 3600.0


def build_simulation_environment(
    config: SimulationEnvironmentConfig | None = None,
) -> SimulationEnvironment:
    config = config or SimulationEnvironmentConfig()

    service_spec = (
        automated_service_spec()
        if config.use_automated_swap
        else default_service_spec()
    )

    routes = prune_corridors(
        top_n=config.route_count,
        sim_hour=config.sim_hour,
        buildings_csv=config.buildings_csv,
    )
    sizing_results = size_hubs(routes, service_spec=service_spec)
    sizing_results = _apply_pad_override(sizing_results, config.pad_override)

    active_hub_ids = sorted(
        {route.corridor.origin.id for route in routes}
        | {route.corridor.destination.id for route in routes}
    )
    hubs_lookup = {hub_id: HUB_LOOKUP[hub_id] for hub_id in active_hub_ids}
    network_peak_orders_per_hour = sum(result.lambda_per_hour for result in sizing_results)
    network_peak_orders_per_hour *= config.demand_scale

    return SimulationEnvironment(
        config=config,
        routes=routes,
        sizing_results=sizing_results,
        hubs_lookup=hubs_lookup,
        service_spec=service_spec,
        network_peak_orders_per_hour=network_peak_orders_per_hour,
    )


def create_registry(
    environment: SimulationEnvironment,
    rl_bridge: "RLBridge | None" = None,
) -> DroneRegistry:
    dispatcher = Dispatcher(
        shortlist=environment.routes,
        lambda_per_sim_s=environment.lambda_per_sim_s,
    )
    fleet_pool = FleetPool.from_hub_sizing(
        environment.sizing_results,
        total_fleet_size=environment.config.fleet_size,
    )
    return DroneRegistry(
        hub_sizing_results=environment.sizing_results,
        dispatcher=dispatcher,
        fleet_pool=fleet_pool,
        rl_bridge=rl_bridge,
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

