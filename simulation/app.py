"""
Sky Burrito — Live Drone Network Simulation
==========================================

Run from the project root:
    uv run streamlit run simulation/app.py

Controls (sidebar)
------------------
  Time multiplier  : 1× → 120×  (1 real-sec = N sim-sec)
  Demand scale     : 0.5× → 3×  (scale λ up/down from baseline 200/hr)
  k override       : use M/G/k recommended pads, or force a lower value
                     (the "what if we under-build?" experiment)
  Start / Pause / Reset

Layout
------
  Left   : Pydeck map — corridors, hubs, live drone dots, craning rings
  Right  : Live metrics — active drones, craning count, per-hub pad utilisation
"""

import sys
import time
from pathlib import Path

import streamlit as st
import pydeck as pdk

# ── Path setup ───────────────────────────────────────────────────────────────
# Allow imports from the project root when running via `streamlit run simulation/app.py`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.config import (
    MAP_BEARING, MAP_CENTER_LAT, MAP_CENTER_LON, MAP_STYLE, MAP_ZOOM, MAP_PITCH,
    TIME_MULTIPLIER, TICK_REAL_S,
)
from simulation.clock import SimClock
from simulation.environment import (
    SimulationRuntimeConfig,
    SimulationSetupConfig,
    build_runtime_environment,
    create_registry,
    load_simulation_setup,
    load_or_build_simulation_setup,
)
from simulation.rl_bridge import RLBridge
from simulation.layers import (
    corridor_arc_layer,
    hub_scatter_layer,
    hub_label_layer,
    saturated_hub_ring_layer,
    drone_layer,
    craning_ring_layer,
)
from settings.paths import SIMULATION_SETUP_JSON
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
    NETWORK_PEAK_ORDERS_PER_HOUR,
)
from settings.simulation import DEFAULT_FLEET_SIZE, RL_FLEET_SIZES

_SETUP_PATH_EXISTS = SIMULATION_SETUP_JSON.exists()
_SETUP_BASELINE_ORDERS_PER_HOUR = (
    load_simulation_setup(SIMULATION_SETUP_JSON).network_peak_orders_per_hour
    if _SETUP_PATH_EXISTS
    else NETWORK_PEAK_ORDERS_PER_HOUR
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sky Burrito — Live Simulation",
    page_icon="🌯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(122, 184, 255, 0.10), transparent 34%),
            linear-gradient(180deg, #f7f9fc 0%, #eef3f8 100%);
    }
    .block-container {
        padding-top: 1.15rem;
        padding-bottom: 1.5rem;
        max-width: 1480px;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fbff 0%, #eef3f8 100%);
        border-right: 1px solid rgba(40, 62, 92, 0.08);
    }
    .sim-hero {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 1.5rem;
        margin-bottom: 0.5rem;
    }
    .sim-kicker {
        font-size: 0.82rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #54708d;
        font-weight: 700;
        margin-bottom: 0.4rem;
    }
    .sim-title {
        font-size: clamp(2.35rem, 4vw, 3.6rem);
        line-height: 0.95;
        letter-spacing: -0.04em;
        color: #1d2736;
        font-weight: 800;
        margin: 0;
    }
    .sim-subtitle {
        color: #63758a;
        font-size: 1rem;
        max-width: 52rem;
        margin: 0.65rem 0 0;
    }
    .sim-chipbar {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        margin: 0.85rem 0 1rem;
    }
    .sim-chip {
        padding: 0.42rem 0.72rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(52, 83, 112, 0.12);
        color: #2d4158;
        font-size: 0.9rem;
        box-shadow: 0 10px 30px rgba(45, 65, 88, 0.05);
    }
    .sim-chip strong {
        color: #142132;
    }
    .sim-status-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.8rem;
        margin: 0 0 0.9rem;
    }
    .sim-status-card {
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(54, 82, 110, 0.1);
        border-radius: 18px;
        padding: 0.9rem 1rem;
        box-shadow: 0 16px 40px rgba(34, 51, 84, 0.08);
        backdrop-filter: blur(10px);
    }
    .sim-status-label {
        color: #708398;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sim-status-value {
        color: #152235;
        font-size: 1.7rem;
        line-height: 1;
        font-weight: 800;
    }
    .sim-status-meta {
        color: #6d7f93;
        font-size: 0.88rem;
        margin-top: 0.35rem;
    }
    .sim-map-frame {
        background: rgba(255, 255, 255, 0.68);
        border: 1px solid rgba(42, 65, 93, 0.08);
        border-radius: 24px;
        padding: 0.75rem 0.75rem 0.35rem;
        box-shadow: 0 24px 60px rgba(40, 58, 86, 0.12);
        margin-bottom: 1rem;
    }
    .featured-route {
        background: linear-gradient(135deg, rgba(18, 35, 60, 0.96), rgba(34, 84, 148, 0.92));
        border: 1px solid rgba(101, 147, 210, 0.30);
        border-radius: 28px;
        padding: 1.15rem 1.25rem;
        box-shadow: 0 26px 70px rgba(20, 45, 84, 0.18);
        color: #f4f8fd;
        margin: 0.2rem 0 1rem;
        overflow: hidden;
        position: relative;
    }
    .featured-route::after {
        content: "";
        position: absolute;
        inset: auto -8% -28% auto;
        width: 220px;
        height: 220px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 176, 73, 0.34), rgba(255, 176, 73, 0.02) 68%);
        pointer-events: none;
    }
    .featured-kicker {
        font-size: 0.78rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        font-weight: 800;
        color: #b9d5fb;
        margin-bottom: 0.28rem;
    }
    .featured-title {
        font-size: clamp(1.55rem, 3vw, 2.35rem);
        font-weight: 800;
        line-height: 1.02;
        margin: 0 0 0.45rem;
        letter-spacing: -0.03em;
    }
    .featured-copy {
        color: rgba(240, 246, 255, 0.90);
        font-size: 1rem;
        line-height: 1.5;
        max-width: 52rem;
        margin: 0 0 0.95rem;
    }
    .featured-metrics {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.7rem;
    }
    .featured-metric {
        background: rgba(255, 255, 255, 0.12);
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 18px;
        padding: 0.8rem 0.9rem;
        backdrop-filter: blur(8px);
    }
    .featured-metric-label {
        color: rgba(215, 230, 255, 0.80);
        font-size: 0.74rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .featured-metric-value {
        color: #ffffff;
        font-size: 1.28rem;
        font-weight: 800;
        line-height: 1.05;
    }
    .route-card {
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(54, 82, 110, 0.10);
        border-radius: 18px;
        padding: 0.9rem 1rem;
        box-shadow: 0 14px 36px rgba(34, 51, 84, 0.08);
        margin-bottom: 0.75rem;
    }
    .route-card.route-card-active {
        border-color: rgba(255, 153, 51, 0.75);
        box-shadow: 0 18px 40px rgba(255, 153, 51, 0.16);
        background: linear-gradient(180deg, rgba(255, 250, 242, 0.98), rgba(255, 255, 255, 0.90));
    }
    .route-rank {
        color: #5e7288;
        font-size: 0.75rem;
        font-weight: 800;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        margin-bottom: 0.18rem;
    }
    .route-title {
        color: #172335;
        font-size: 1.02rem;
        font-weight: 800;
        margin-bottom: 0.35rem;
    }
    .route-meta {
        color: #5f7389;
        font-size: 0.9rem;
        line-height: 1.5;
    }
    @media (max-width: 900px) {
        .sim-hero {
            display: block;
        }
        .sim-status-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .featured-metrics {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Cache expensive startup work ──────────────────────────────────────────────
@st.cache_resource
def load_environment(
    demand_scale: float = 1.0,
    use_auto_swap: bool = False,
    pad_override: int = 0,
    fleet_size: int = DEFAULT_FLEET_SIZE,
):
    """
    Load the persisted setup and build the runtime environment for the app.
    """
    if _SETUP_PATH_EXISTS:
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
        _ROOT / "models" / f"fleet_{fleet_size}"
        / f"ppo_fleet_{fleet_size}_phase_3.zip"
    )
    return RLBridge(model_path=model_path, fleet_size=fleet_size, enabled=True)


# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌯 Sky Burrito")
    st.caption("SF Inter-District Drone Network Simulation")
    st.divider()

    time_mult = st.slider(
        "⏩ Time multiplier",
        min_value=1, max_value=120, value=int(TIME_MULTIPLIER), step=1,
        help="1 real second = N simulation seconds",
    )

    demand_scale = st.slider(
        f"📦 Demand scale (×baseline {_SETUP_BASELINE_ORDERS_PER_HOUR:.0f}/hr)",
        min_value=0.5, max_value=3.0, value=float(DEFAULT_DEMAND_SCALE), step=0.1,
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
        min_value=0, max_value=10, value=0,
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
    btn_start = col1.button("▶ Start",  use_container_width=True)
    btn_pause = col2.button("⏸ Pause", use_container_width=True)
    btn_reset = col3.button("↺ Reset",  use_container_width=True)

    st.divider()
    st.caption("**Color legend**")
    st.markdown("""
- 🟡 TAKEOFF
- 🔵 CRUISE
- 🟠 LANDING
- 🟢 COOLDOWN
- 🔴 **CRANING** ← the bottleneck
- ⬛ IDLE
""")

# ── Session state initialisation ──────────────────────────────────────────────
if "running" not in st.session_state:
    st.session_state.running = False
if "clock" not in st.session_state:
    st.session_state.clock = None
if "registry" not in st.session_state:
    st.session_state.registry = None
if "snapshot" not in st.session_state:
    st.session_state.snapshot = None
if "rl_bridge" not in st.session_state:
    st.session_state.rl_bridge = None

# ── Button logic ─────────────────────────────────────────────────────────────
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
elif top_routes and st.session_state.selected_route_label not in {r.corridor.label for r in top_routes}:
    st.session_state.selected_route_label = top_routes[0].corridor.label


def _selected_route():
    for rank, route in enumerate(top_routes, start=1):
        if route.corridor.label == st.session_state.get("selected_route_label"):
            return rank, route
    if top_routes:
        return 1, top_routes[0]
    return None, None

if btn_reset or (btn_start and st.session_state.registry is None):
    clock = SimClock(time_multiplier=time_mult)
    bridge = load_rl_bridge(fleet_size=rl_fleet_size, enabled=rl_enabled)
    registry = create_registry(environment, rl_bridge=bridge if rl_enabled else None)
    st.session_state.clock     = clock
    st.session_state.registry  = registry
    st.session_state.rl_bridge = bridge
    st.session_state.running   = not btn_reset
    st.session_state.snapshot  = None

if btn_start:
    st.session_state.running = True
if btn_pause:
    st.session_state.running = False

# ── Main layout ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="sim-hero">
      <div>
        <div class="sim-kicker">San Francisco Digital Twin</div>
        <h1 class="sim-title">Live Network Map</h1>
        <p class="sim-subtitle">
          Real hub locations, live vehicle states, and visible bottlenecks across the evening peak window.
        </p>
      </div>
    </div>
    <div class="sim-chipbar">
      <div class="sim-chip"><strong>Heavy</strong> hubs in red</div>
      <div class="sim-chip"><strong>Moderate</strong> hubs in amber</div>
      <div class="sim-chip"><strong>Light</strong> hubs in green</div>
      <div class="sim-chip"><strong>Red halos</strong> mark saturated hubs</div>
      <div class="sim-chip"><strong>Blue arcs</strong> show corridor demand</div>
    </div>
    """,
    unsafe_allow_html=True,
)

map_placeholder     = st.empty()
metrics_placeholder = st.empty()
story_placeholder   = st.empty()

# ── Initial / static map (shown before simulation starts) ────────────────────
def _initial_view() -> pdk.Deck:
    arc_layer   = corridor_arc_layer(top_routes, st.session_state.selected_route_label)
    hub_layer   = hub_scatter_layer(sizing, {}, active_hubs_lookup)
    label_layer = hub_label_layer(sizing, active_hubs_lookup)
    return pdk.Deck(
        layers=[arc_layer, hub_layer, label_layer],
        initial_view_state=pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=MAP_ZOOM,
            pitch=MAP_PITCH,
            bearing=MAP_BEARING,
        ),
        map_provider="carto",
        map_style=MAP_STYLE,
        tooltip={
            "html": "<b>{label}</b><br/>Δt saved: {time_delta_min} min<br/>"
                    "Energy edge: {energy_ratio}×<br/>Composite score: {score}",
            "style": {"backgroundColor": "#102033", "color": "white"},
        },
    )


def _live_view(snapshot) -> pdk.Deck:
    arc_layer    = corridor_arc_layer(top_routes, st.session_state.selected_route_label)
    hub_s_layer  = hub_scatter_layer(sizing, snapshot.hub_metrics, active_hubs_lookup)
    label_layer  = hub_label_layer(sizing, active_hubs_lookup)
    halo_layer   = saturated_hub_ring_layer(sizing, snapshot.hub_metrics, active_hubs_lookup)
    d_layer      = drone_layer(snapshot)
    cran_layer   = craning_ring_layer(snapshot)
    return pdk.Deck(
        layers=[arc_layer, halo_layer, hub_s_layer, label_layer, d_layer, cran_layer],
        initial_view_state=pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=MAP_ZOOM,
            pitch=MAP_PITCH,
            bearing=MAP_BEARING,
        ),
        map_provider="carto",
        map_style=MAP_STYLE,
        tooltip={
            "html": (
                "<b>{state}</b> Drone #{drone_id}<br/>"
                "Hub {origin_id} → Hub {dest_id}<br/>"
                "Progress: {progress}<br/>"
                "Craning: {craning_s}s"
            ),
            "style": {"backgroundColor": "#102033", "color": "white"},
        },
    )


def _render_featured_route() -> None:
    with story_placeholder.container():
        rank, route = _selected_route()
        if not route:
            st.caption("No featured route is available yet.")
            return

        story = (
            "This corridor is featured because it combines strong demand, meaningful time savings, "
            "and a clear energy advantage over ground delivery."
        )
        st.markdown(
            f"""
            <div class="featured-route">
              <div class="featured-kicker">Featured Route</div>
              <div class="featured-title">{route.corridor.label}</div>
              <p class="featured-copy">
                {story}
              </p>
              <div class="featured-metrics">
                <div class="featured-metric">
                  <div class="featured-metric-label">Top-10 Rank</div>
                  <div class="featured-metric-value">#{rank}</div>
                </div>
                <div class="featured-metric">
                  <div class="featured-metric-label">Time Saved</div>
                  <div class="featured-metric-value">{route.time_delta_s / 60:.1f} min</div>
                </div>
                <div class="featured-metric">
                  <div class="featured-metric-label">Energy Advantage</div>
                  <div class="featured-metric-value">{route.energy_ratio:.2f}x</div>
                </div>
                <div class="featured-metric">
                  <div class="featured-metric-label">Demand Weight</div>
                  <div class="featured-metric-value">{route.demand_weight:,}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_metrics(snapshot) -> None:
    bridge: RLBridge | None = st.session_state.get("rl_bridge")
    rl_active = bridge is not None and bridge.is_available

    with metrics_placeholder.container():
        # ── Top status cards ───────────────────────────────────────────────
        rl_badge = (
            f'<span style="color:#5bb85b;font-size:0.75rem;font-weight:700;">'
            f'● PPO active (fleet {bridge.fleet_size if bridge else "—"})</span>'
            if rl_active else
            '<span style="color:#a0aab4;font-size:0.75rem;">○ PPO off</span>'
        )
        rl_moves_label = (
            f"{snapshot.rl_drones_rebalanced} drones repositioned"
            if rl_active else "Enable in sidebar"
        )

        st.markdown(
            f"""
            <div class="sim-status-grid" style="grid-template-columns:repeat(5,minmax(0,1fr));">
              <div class="sim-status-card">
                <div class="sim-status-label">Sim Time</div>
                <div class="sim-status-value">{snapshot.sim_time_hhmm}</div>
                <div class="sim-status-meta">Friday peak window</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Active Drones</div>
                <div class="sim-status-value">{snapshot.total_active_drones}</div>
                <div class="sim-status-meta">{snapshot.fleet.total_idle} idle at hubs</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Queued Orders</div>
                <div class="sim-status-value">{snapshot.fleet.total_queued_orders}</div>
                <div class="sim-status-meta">{snapshot.total_orders_dispatched} flights launched</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Craning Now</div>
                <div class="sim-status-value">{snapshot.total_craning}</div>
                <div class="sim-status-meta">{snapshot.total_craning_events} total events</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">RL Rebalancing {rl_badge}</div>
                <div class="sim-status-value">{snapshot.rl_rebalancing_moves}</div>
                <div class="sim-status-meta">{rl_moves_label}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── RL load error banner ───────────────────────────────────────────
        if bridge and not bridge.is_available and bridge.load_error:
            st.warning(f"⚠️ RL model unavailable: {bridge.load_error}", icon="🤖")


        st.divider()
        st.markdown("**Hub pad utilisation**")
        cols = st.columns(5)
        sorted_hubs = sorted(snapshot.hub_metrics.items(), key=lambda x: -x[1].utilisation_pct)
        for i, (hub_id, m) in enumerate(sorted_hubs):
            col = cols[i % 5]
            icon = "🔴" if m.is_saturated else ("🟡" if m.utilisation_pct > 60 else "🟢")
            col.metric(
                f"{icon} Hub {hub_id}",
                f"{m.utilisation_pct:.0f}%",
                f"{m.pads_in_use}/{m.k_pads} pads  {m.drones_craning} craning",
                delta_color="inverse",
            )

        st.divider()
        st.markdown("**Supporting Top 10 corridor list**")
        st.caption(f"Demo network is limited to {len(top_routes)} top-ranked corridors across {len(active_hub_ids)} active hubs.")
        route_options = {route.corridor.label: route for route in top_routes}

        if route_options:
            st.selectbox(
                "Featured route on map",
                options=list(route_options.keys()),
                key="selected_route_label",
                help="Choose which top-ranked corridor is featured in the story panel and highlighted on the map.",
            )
            for rank, route in enumerate(top_routes, start=1):
                is_active = route.corridor.label == st.session_state.selected_route_label
                st.markdown(
                    f"""
                    <div class="route-card {'route-card-active' if is_active else ''}">
                      <div class="route-rank">Rank #{rank}</div>
                      <div class="route-title">{route.corridor.label}</div>
                      <div class="route-meta">
                        {route.time_delta_s / 60:.1f} min faster than ground<br/>
                        Energy advantage: {route.energy_ratio:.2f}×<br/>
                        Demand weight: {route.demand_weight:,}<br/>
                        Composite score: {route.composite_score:,.0f}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No shortlisted corridors are available for ranking display.")


# ── Render loop ───────────────────────────────────────────────────────────────
if not st.session_state.running or st.session_state.registry is None:
    _render_featured_route()
    with map_placeholder.container():
        st.markdown('<div class="sim-map-frame">', unsafe_allow_html=True)
        st.pydeck_chart(_initial_view())
        st.markdown("</div>", unsafe_allow_html=True)
    if st.session_state.snapshot:
        _render_metrics(st.session_state.snapshot)
    else:
        st.info("Press **▶ Start** to begin the Friday night simulation.")

else:
    clock    = st.session_state.clock
    registry = st.session_state.registry

    clock.set_multiplier(time_mult)
    clock.tick()

    snapshot = registry.tick(
        dt_sim_s     = clock.tick_sim_s,
        sim_time_hhmm= clock.hhmm,
    )

    st.session_state.snapshot = snapshot

    _render_featured_route()
    with map_placeholder.container():
        st.markdown('<div class="sim-map-frame">', unsafe_allow_html=True)
        st.pydeck_chart(_live_view(snapshot))
        st.markdown("</div>", unsafe_allow_html=True)
    _render_metrics(snapshot)

    time.sleep(TICK_REAL_S)
    st.rerun()
