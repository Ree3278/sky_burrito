"""Shared simulation setup and runtime environment assembly."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from corridor_pruning.corridors import Corridor
from corridor_pruning.hubs import HUB_LOOKUP, Hub
from corridor_pruning.pruning import ScoredCorridor, prune_corridors
from hub_sizing.service import ServiceSpec, automated_service_spec, default_service_spec
from hub_sizing.sizing import HubSizingResult, size_hubs
from settings.paths import BUILDINGS_CSV, SIMULATION_SETUP_JSON
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
)
from settings.rl import ACTIVE_HUBS as RL_ACTIVE_HUBS
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.dispatcher import Dispatcher
from simulation.fleet import FleetPool
from simulation.registry import DroneRegistry

if TYPE_CHECKING:
    from simulation.rl_bridge import RLBridge


@dataclass(frozen=True)
class SimulationSetupConfig:
    route_count: int = DEFAULT_PRUNED_CORRIDOR_COUNT
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR
    use_automated_swap: bool = False
    buildings_csv: Optional[str] = str(BUILDINGS_CSV)
    allowed_hub_names: Optional[List[str]] = None


@dataclass(frozen=True)
class SimulationRuntimeConfig:
    demand_scale: float = DEFAULT_DEMAND_SCALE
    pad_override: int = 0
    fleet_size: int = DEFAULT_FLEET_SIZE


@dataclass(frozen=True)
class SimulationEnvironmentConfig:
    route_count: int = DEFAULT_PRUNED_CORRIDOR_COUNT
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR
    demand_scale: float = DEFAULT_DEMAND_SCALE
    use_automated_swap: bool = False
    pad_override: int = 0
    fleet_size: int = DEFAULT_FLEET_SIZE
    buildings_csv: Optional[str] = str(BUILDINGS_CSV)
    allowed_hub_names: Optional[List[str]] = None

    def setup_config(self) -> SimulationSetupConfig:
        return SimulationSetupConfig(
            route_count=self.route_count,
            sim_hour=self.sim_hour,
            use_automated_swap=self.use_automated_swap,
            buildings_csv=self.buildings_csv,
            allowed_hub_names=self.allowed_hub_names,
        )

    def runtime_config(self) -> SimulationRuntimeConfig:
        return SimulationRuntimeConfig(
            demand_scale=self.demand_scale,
            pad_override=self.pad_override,
            fleet_size=self.fleet_size,
        )


@dataclass(frozen=True)
class RouteSetup:
    origin_id: int
    destination_id: int
    straight_line_m: float
    bearing_deg: float
    obstacle_height_m: Optional[float]
    drone_time_s: float
    ground_time_s: float
    time_delta_s: float
    road_distance_m: float
    detour_ratio: float
    drone_energy_wh: float
    ground_energy_wh: float
    energy_ratio: float
    demand_weight: int
    ground_cost_usd: float
    drone_cost_usd: float
    cost_arbitrage_usd: float
    cost_ratio: float
    uber_payout_breakdown: Dict[str, float]
    drone_co2_g: float
    ground_co2_g: float
    co2_saved_g: float
    co2_reduction_pct: float
    composite_score: float
    used_stubs: bool


@dataclass(frozen=True)
class HubSetup:
    hub_id: int
    lat: float
    lon: float
    restaurants_nearby: int
    resunits_nearby: int
    lambda_per_hour: float
    offered_load: float
    k_pads: int
    k_bays: int
    utilisation_pct: float
    p_cran_pct: float
    p_cran_minus1_pct: float
    tier: str
    binding_constraint: str
    is_stub: bool

    @property
    def name(self) -> str:
        return f"Hub {self.hub_id}"


@dataclass(frozen=True)
class SimulationSetup:
    config: SimulationSetupConfig
    service_mean_s: float
    service_cv_squared: float
    network_peak_orders_per_hour: float
    routes: List[RouteSetup]
    hubs: List[HubSetup]

    @property
    def active_hub_ids(self) -> List[int]:
        return [hub.hub_id for hub in self.hubs]

    @property
    def active_hub_names(self) -> List[str]:
        return [hub.name for hub in self.hubs]

    def to_dict(self) -> dict:
        return {
            "config": asdict(self.config),
            "service_mean_s": self.service_mean_s,
            "service_cv_squared": self.service_cv_squared,
            "network_peak_orders_per_hour": self.network_peak_orders_per_hour,
            "routes": [asdict(route) for route in self.routes],
            "hubs": [asdict(hub) for hub in self.hubs],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "SimulationSetup":
        return cls(
            config=SimulationSetupConfig(
                route_count=payload["config"].get("route_count", DEFAULT_PRUNED_CORRIDOR_COUNT),
                sim_hour=payload["config"].get("sim_hour", DEFAULT_CORRIDOR_SIM_HOUR),
                use_automated_swap=payload["config"].get("use_automated_swap", False),
                buildings_csv=payload["config"].get("buildings_csv", str(BUILDINGS_CSV)),
                allowed_hub_names=payload["config"].get("allowed_hub_names"),
            ),
            service_mean_s=float(payload["service_mean_s"]),
            service_cv_squared=float(payload["service_cv_squared"]),
            network_peak_orders_per_hour=float(payload["network_peak_orders_per_hour"]),
            routes=[RouteSetup(**route) for route in payload["routes"]],
            hubs=[HubSetup(**hub) for hub in payload["hubs"]],
        )


@dataclass(frozen=True)
class SimulationEnvironment:
    setup: SimulationSetup
    runtime_config: SimulationRuntimeConfig
    routes: List[ScoredCorridor]
    sizing_results: List[HubSizingResult]
    hubs_lookup: Dict[int, Hub]

    @property
    def active_hub_ids(self) -> List[int]:
        return self.setup.active_hub_ids

    @property
    def active_hub_names(self) -> List[str]:
        return self.setup.active_hub_names

    @property
    def network_peak_orders_per_hour(self) -> float:
        return self.setup.network_peak_orders_per_hour * self.runtime_config.demand_scale

    @property
    def lambda_per_sim_s(self) -> float:
        return self.network_peak_orders_per_hour / 3600.0

    @property
    def config(self) -> SimulationEnvironmentConfig:
        return SimulationEnvironmentConfig(
            route_count=self.setup.config.route_count,
            sim_hour=self.setup.config.sim_hour,
            demand_scale=self.runtime_config.demand_scale,
            use_automated_swap=self.setup.config.use_automated_swap,
            pad_override=self.runtime_config.pad_override,
            fleet_size=self.runtime_config.fleet_size,
            buildings_csv=self.setup.config.buildings_csv,
            allowed_hub_names=self.setup.config.allowed_hub_names,
        )


def build_simulation_setup(
    config: SimulationSetupConfig | None = None,
) -> SimulationSetup:
    config = config or SimulationSetupConfig()
    service_spec = _service_spec_from_config(config)

    routes = prune_corridors(
        top_n=config.route_count,
        sim_hour=config.sim_hour,
        buildings_csv=config.buildings_csv,
    )
    allowed_hub_names = set(config.allowed_hub_names or RL_ACTIVE_HUBS)
    routes = [
        route
        for route in routes
        if f"Hub {route.corridor.origin.id}" in allowed_hub_names
        and f"Hub {route.corridor.destination.id}" in allowed_hub_names
    ][: config.route_count]
    sizing_results = size_hubs(routes, service_spec=service_spec)

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
        routes=[_route_setup_from_scored(route) for route in routes],
        hubs=[hub_lookup[hub_id] for hub_id in sorted(hub_lookup)],
    )


def build_runtime_environment(
    setup: SimulationSetup,
    runtime_config: SimulationRuntimeConfig | None = None,
) -> SimulationEnvironment:
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
    config = config or SimulationEnvironmentConfig()
    setup = build_simulation_setup(config.setup_config())
    return build_runtime_environment(setup, config.runtime_config())


def save_simulation_setup(
    setup: SimulationSetup,
    path: str | Path = SIMULATION_SETUP_JSON,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(setup.to_dict(), indent=2), encoding="utf-8")
    return path


def load_simulation_setup(
    path: str | Path = SIMULATION_SETUP_JSON,
) -> SimulationSetup:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SimulationSetup.from_dict(payload)


def load_or_build_simulation_setup(
    config: SimulationSetupConfig | None = None,
    path: str | Path = SIMULATION_SETUP_JSON,
    persist_if_built: bool = True,
) -> SimulationSetup:
    path = Path(path)
    if path.exists():
        existing = load_simulation_setup(path)
        if config is None or existing.config == config:
            return existing
        setup = build_simulation_setup(config)
        if persist_if_built:
            save_simulation_setup(setup, path)
        return setup

    setup = build_simulation_setup(config)
    if persist_if_built:
        save_simulation_setup(setup, path)
    return setup


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
