"""
Sky Burrito — Live Drone Network Simulation
==========================================

Run from the project root:
    uv run streamlit run simulation/app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from settings.paths import SIMULATION_SETUP_JSON
from settings.simulation import DEFAULT_FLEET_SIZE, RL_FLEET_SIZES
from simulation.app_support import (
    APP_STYLE,
    baseline_orders_per_hour,
    build_initial_view,
    build_live_view,
    ensure_session_state,
    handle_control_buttons,
    load_environment,
    render_featured_route,
    render_header,
    render_metrics,
    selected_route,
)
from simulation.config import (
    MAP_BEARING,
    MAP_CENTER_LAT,
    MAP_CENTER_LON,
    MAP_PITCH,
    MAP_STYLE,
    MAP_ZOOM,
    TICK_REAL_S,
    TIME_MULTIPLIER,
)

_SETUP_PATH_EXISTS = SIMULATION_SETUP_JSON.exists()
_SETUP_BASELINE_ORDERS_PER_HOUR = baseline_orders_per_hour()
_VIEW_STATE = {
    "latitude": MAP_CENTER_LAT,
    "longitude": MAP_CENTER_LON,
    "zoom": MAP_ZOOM,
    "pitch": MAP_PITCH,
    "bearing": MAP_BEARING,
}

st.set_page_config(
    page_title="Sky Burrito — Live Simulation",
    page_icon="🌯",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_STYLE, unsafe_allow_html=True)

with st.sidebar:
    st.title("🌯 Sky Burrito")
    st.caption("SF Inter-District Drone Network Simulation")
    st.divider()

    time_mult = st.slider(
        "⏩ Time multiplier",
        min_value=1,
        max_value=120,
        value=int(TIME_MULTIPLIER),
        step=1,
        help="1 real second = N simulation seconds",
    )
    demand_scale = st.slider(
        f"📦 Demand scale (×baseline {_SETUP_BASELINE_ORDERS_PER_HOUR:.0f}/hr)",
        min_value=0.5,
        max_value=3.0,
        value=1.0,
        step=0.1,
    )
    use_auto_swap = st.toggle(
        "🤖 Automated battery swap (3.5 min)",
        value=False,
        disabled=_SETUP_PATH_EXISTS,
        help=(
            f"Disabled while using persisted setup at {SIMULATION_SETUP_JSON}."
            if _SETUP_PATH_EXISTS
            else "Rebuild the network setup with the faster service-time assumption."
        ),
    )
    pad_override = st.slider(
        "▣ Pad count override (0 = use M/G/k recommendation)",
        min_value=0,
        max_value=10,
        value=0,
        help="Force a pad count on every hub to explore craning behavior",
    )

    st.divider()
    st.caption("**🤖 RL Fleet Rebalancing**")
    rl_enabled = st.toggle(
        "Enable PPO rebalancing agent",
        value=False,
        help=(
            "Loads the trained PPO model and fires a rebalancing action "
            "every 60 simulated seconds. Drones are redistributed across "
            "hubs to prevent tidal flow build-up."
        ),
    )
    rl_fleet_size = st.select_slider(
        "Fleet size (model variant)",
        options=list(RL_FLEET_SIZES),
        value=20,
        help="Which trained model variant to use. Fleet 20 ran the full 3-phase curriculum.",
        disabled=not rl_enabled,
    )

    st.divider()
    col1, col2, col3 = st.columns(3)
    btn_start = col1.button("▶ Start", use_container_width=True)
    btn_pause = col2.button("⏸ Pause", use_container_width=True)
    btn_reset = col3.button("↺ Reset", use_container_width=True)

    st.divider()
    st.caption("**Color legend**")
    st.markdown(
        """
- 🟡 TAKEOFF
- 🔵 CRUISE
- 🟠 LANDING
- 🟢 COOLDOWN
- 🔴 **CRANING** ← the bottleneck
- ⬛ IDLE
"""
    )

ensure_session_state()

fleet_size = rl_fleet_size if rl_enabled else DEFAULT_FLEET_SIZE
environment = load_environment(
    demand_scale=demand_scale,
    use_auto_swap=use_auto_swap,
    pad_override=pad_override,
    fleet_size=fleet_size,
)
top_routes = environment.routes
sizing = environment.sizing_results
active_hubs_lookup = environment.hubs_lookup
active_hub_ids = environment.active_hub_ids

if "selected_route_label" not in st.session_state and top_routes:
    st.session_state.selected_route_label = top_routes[0].corridor.label
elif top_routes and st.session_state.selected_route_label not in {
    route.corridor.label for route in top_routes
}:
    st.session_state.selected_route_label = top_routes[0].corridor.label

handle_control_buttons(
    btn_start=btn_start,
    btn_pause=btn_pause,
    btn_reset=btn_reset,
    environment=environment,
    time_mult=time_mult,
    rl_enabled=rl_enabled,
    rl_fleet_size=rl_fleet_size,
)

render_header()
map_placeholder = st.empty()
metrics_placeholder = st.empty()
story_placeholder = st.empty()

if not st.session_state.running or st.session_state.registry is None:
    rank, route = selected_route(top_routes)
    render_featured_route(story_placeholder, rank=rank, route=route)
    with map_placeholder.container():
        st.markdown('<div class="sim-map-frame">', unsafe_allow_html=True)
        st.pydeck_chart(
            build_initial_view(
                top_routes=top_routes,
                selected_route_label=st.session_state.get("selected_route_label"),
                sizing=sizing,
                active_hubs_lookup=active_hubs_lookup,
                view_state=_VIEW_STATE,
                map_style=MAP_STYLE,
            )
        )
        st.markdown("</div>", unsafe_allow_html=True)
    if st.session_state.snapshot:
        render_metrics(
            metrics_placeholder,
            snapshot=st.session_state.snapshot,
            bridge=st.session_state.get("rl_bridge"),
            top_routes=top_routes,
            active_hub_ids=active_hub_ids,
        )
    else:
        st.info("Press **▶ Start** to begin the Friday night simulation.")
else:
    clock = st.session_state.clock
    registry = st.session_state.registry

    clock.set_multiplier(time_mult)
    clock.tick()

    snapshot = registry.tick(
        dt_sim_s=clock.tick_sim_s,
        sim_time_hhmm=clock.hhmm,
    )
    st.session_state.snapshot = snapshot

    rank, route = selected_route(top_routes)
    render_featured_route(story_placeholder, rank=rank, route=route)
    with map_placeholder.container():
        st.markdown('<div class="sim-map-frame">', unsafe_allow_html=True)
        st.pydeck_chart(
            build_live_view(
                snapshot=snapshot,
                top_routes=top_routes,
                selected_route_label=st.session_state.get("selected_route_label"),
                sizing=sizing,
                active_hubs_lookup=active_hubs_lookup,
                view_state=_VIEW_STATE,
                map_style=MAP_STYLE,
            )
        )
        st.markdown("</div>", unsafe_allow_html=True)
    render_metrics(
        metrics_placeholder,
        snapshot=snapshot,
        bridge=st.session_state.get("rl_bridge"),
        top_routes=top_routes,
        active_hub_ids=active_hub_ids,
    )

    time.sleep(TICK_REAL_S)
    st.rerun()
