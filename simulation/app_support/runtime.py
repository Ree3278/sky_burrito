"""Runtime helpers for the Streamlit simulation app."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from settings.paths import SIMULATION_SETUP_JSON
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
    NETWORK_PEAK_ORDERS_PER_HOUR,
)
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.clock import SimClock
from simulation.environment import (
    SimulationRuntimeConfig,
    SimulationSetupConfig,
    build_runtime_environment,
    create_registry,
    load_or_build_simulation_setup,
    load_simulation_setup,
)
from simulation.rl_bridge import RLBridge

_ROOT = Path(__file__).resolve().parents[2]


def baseline_orders_per_hour() -> float:
    """Return the baseline network peak rate shown in the sidebar."""
    if SIMULATION_SETUP_JSON.exists():
        return load_simulation_setup(SIMULATION_SETUP_JSON).network_peak_orders_per_hour
    return NETWORK_PEAK_ORDERS_PER_HOUR


@st.cache_resource
def load_environment(
    demand_scale: float = 1.0,
    use_auto_swap: bool = False,
    pad_override: int = 0,
    fleet_size: int = DEFAULT_FLEET_SIZE,
):
    """Load the persisted setup and convert it to a runtime environment."""
    if SIMULATION_SETUP_JSON.exists():
        setup = load_simulation_setup(SIMULATION_SETUP_JSON)
    else:
        setup = load_or_build_simulation_setup(
            SimulationSetupConfig(
                route_count=DEFAULT_SIMULATION_CORRIDOR_COUNT,
                sim_hour=DEFAULT_CORRIDOR_SIM_HOUR,
                use_automated_swap=use_auto_swap,
            ),
            path=SIMULATION_SETUP_JSON,
            persist_if_built=True,
        )
    return build_runtime_environment(
        setup,
        SimulationRuntimeConfig(
            demand_scale=demand_scale,
            pad_override=pad_override,
            fleet_size=fleet_size,
        ),
    )


@st.cache_resource
def load_rl_bridge(fleet_size: int, enabled: bool) -> RLBridge:
    """Load and cache the PPO rebalancing model for the given fleet size."""
    if not enabled:
        return RLBridge(model_path="", fleet_size=fleet_size, enabled=False)
    model_path = (
        _ROOT / "models" / f"fleet_{fleet_size}" / f"ppo_fleet_{fleet_size}_phase_3.zip"
    )
    return RLBridge(model_path=model_path, fleet_size=fleet_size, enabled=True)


def ensure_session_state() -> None:
    """Initialize the Streamlit session keys used by the simulation app."""
    st.session_state.setdefault("running", False)
    st.session_state.setdefault("clock", None)
    st.session_state.setdefault("registry", None)
    st.session_state.setdefault("snapshot", None)
    st.session_state.setdefault("rl_bridge", None)


def selected_route(top_routes):
    """Return the currently highlighted route and its rank."""
    for rank, route in enumerate(top_routes, start=1):
        if route.corridor.label == st.session_state.get("selected_route_label"):
            return rank, route
    if top_routes:
        return 1, top_routes[0]
    return None, None


def handle_control_buttons(
    *,
    btn_start: bool,
    btn_pause: bool,
    btn_reset: bool,
    environment,
    time_mult: int,
    rl_enabled: bool,
    rl_fleet_size: int,
) -> None:
    """Apply start/pause/reset actions against Streamlit session state."""
    if btn_reset or (btn_start and st.session_state.registry is None):
        clock = SimClock(time_multiplier=time_mult)
        bridge = load_rl_bridge(fleet_size=rl_fleet_size, enabled=rl_enabled)
        registry = create_registry(environment, rl_bridge=bridge if rl_enabled else None)
        st.session_state.clock = clock
        st.session_state.registry = registry
        st.session_state.rl_bridge = bridge
        st.session_state.running = not btn_reset
        st.session_state.snapshot = None

    if btn_start:
        st.session_state.running = True
    if btn_pause:
        st.session_state.running = False


__all__ = [
    "baseline_orders_per_hour",
    "ensure_session_state",
    "handle_control_buttons",
    "load_environment",
    "load_rl_bridge",
    "selected_route",
]
