"""Dataclasses for persisted simulation setup and runtime environment state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from corridor_pruning.hubs import Hub
from corridor_pruning.pruning import ScoredCorridor
from hub_sizing.sizing import HubSizingResult
from settings.paths import BUILDINGS_CSV
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
)
from settings.simulation import DEFAULT_FLEET_SIZE


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


__all__ = [
    "HubSetup",
    "RouteSetup",
    "SimulationEnvironment",
    "SimulationEnvironmentConfig",
    "SimulationRuntimeConfig",
    "SimulationSetup",
    "SimulationSetupConfig",
]
