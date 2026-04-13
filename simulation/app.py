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

from corridor_pruning.pruning import prune_corridors
from corridor_pruning.hubs import HUB_LOOKUP
from hub_sizing.sizing import size_hubs
from hub_sizing.service import default_service_spec, automated_service_spec

from simulation.config import (
    MAP_CENTER_LAT, MAP_CENTER_LON, MAP_ZOOM, MAP_PITCH,
    TIME_MULTIPLIER, TICK_REAL_S,
)
from simulation.clock import SimClock
from simulation.dispatcher import Dispatcher
from simulation.registry import DroneRegistry
from simulation.layers import (
    corridor_arc_layer,
    hub_scatter_layer,
    hub_label_layer,
    drone_layer,
    craning_ring_layer,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sky Burrito — Live Simulation",
    page_icon="🌯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Cache expensive startup work ──────────────────────────────────────────────
@st.cache_resource
def load_network(demand_scale: float = 1.0, use_auto_swap: bool = False):
    """
    Run corridor pruning + hub sizing once and cache the results.
    Re-runs if demand_scale or use_auto_swap changes.
    """
    shortlist = prune_corridors()
    spec = automated_service_spec() if use_auto_swap else default_service_spec()
    sizing = size_hubs(shortlist, service_spec=spec)
    return shortlist, sizing


# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌯 Sky Burrito")
    st.caption("SF Inter-District Drone Network Simulation")
    st.divider()

    time_mult = st.slider(
        "⏩ Time multiplier",
        min_value=1, max_value=120, value=60, step=1,
        help="1 real second = N simulation seconds",
    )

    demand_scale = st.slider(
        "📦 Demand scale (×baseline 200/hr)",
        min_value=0.5, max_value=3.0, value=1.0, step=0.1,
    )

    use_auto_swap = st.toggle("🤖 Automated battery swap (3.5 min)", value=False)

    pad_override = st.slider(
        "▣ Pad count override (0 = use M/G/k recommendation)",
        min_value=0, max_value=10, value=0,
        help="Force a pad count on every hub to explore craning behavior",
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

# ── Button logic ─────────────────────────────────────────────────────────────
shortlist, sizing = load_network(demand_scale, use_auto_swap)

if pad_override > 0:
    for r in sizing:
        r.k_pads = pad_override
        r.k_bays = pad_override

if btn_reset or (btn_start and st.session_state.registry is None):
    clock = SimClock(time_multiplier=time_mult)
    dispatcher = Dispatcher(
        shortlist=shortlist,
        lambda_per_sim_s=(200 * demand_scale) / 3600,
    )
    registry = DroneRegistry(
        hub_sizing_results=sizing,
        dispatcher=dispatcher,
    )
    st.session_state.clock    = clock
    st.session_state.registry = registry
    st.session_state.running  = not btn_reset
    st.session_state.snapshot = None

if btn_start:
    st.session_state.running = True
if btn_pause:
    st.session_state.running = False

# ── Main layout ───────────────────────────────────────────────────────────────
st.markdown("## 🗺️ Live Network Map")

map_placeholder     = st.empty()
metrics_placeholder = st.empty()

# ── Initial / static map (shown before simulation starts) ────────────────────
def _initial_view() -> pdk.Deck:
    arc_layer   = corridor_arc_layer(shortlist)
    hub_layer   = hub_scatter_layer(sizing, {}, HUB_LOOKUP)
    label_layer = hub_label_layer(sizing, HUB_LOOKUP)
    return pdk.Deck(
        layers=[arc_layer, hub_layer, label_layer],
        initial_view_state=pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=MAP_ZOOM,
            pitch=MAP_PITCH,
        ),
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={
            "html": "<b>{label}</b><br/>Δt saved: {time_delta_min} min<br/>"
                    "Hub {hub_id} — {tier} tier<br/>{k_pads} pads  util: {util_pct}%",
            "style": {"backgroundColor": "#1a1a2e", "color": "white"},
        },
    )


def _live_view(snapshot) -> pdk.Deck:
    arc_layer    = corridor_arc_layer(shortlist)
    hub_s_layer  = hub_scatter_layer(sizing, snapshot.hub_metrics, HUB_LOOKUP)
    label_layer  = hub_label_layer(sizing, HUB_LOOKUP)
    d_layer      = drone_layer(snapshot)
    cran_layer   = craning_ring_layer(snapshot)
    return pdk.Deck(
        layers=[arc_layer, hub_s_layer, label_layer, d_layer, cran_layer],
        initial_view_state=pdk.ViewState(
            latitude=MAP_CENTER_LAT,
            longitude=MAP_CENTER_LON,
            zoom=MAP_ZOOM,
            pitch=MAP_PITCH,
        ),
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={
            "html": (
                "<b>{state}</b> Drone #{drone_id}<br/>"
                "Hub {origin_id} → Hub {dest_id}<br/>"
                "Progress: {progress}<br/>"
                "Craning: {craning_s}s"
            ),
            "style": {"backgroundColor": "#1a1a2e", "color": "white"},
        },
    )


def _render_metrics(snapshot) -> None:
    with metrics_placeholder.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🕐 Sim Time",        snapshot.sim_time_hhmm)
        c2.metric("✈️ Active Drones",   snapshot.total_active_drones)
        c3.metric("🔴 Craning Now",     snapshot.total_craning,
                  delta=f"{snapshot.total_craning_events} total events",
                  delta_color="inverse")
        c4.metric("📦 Orders Dispatched", snapshot.total_orders_dispatched)

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


# ── Render loop ───────────────────────────────────────────────────────────────
if not st.session_state.running or st.session_state.registry is None:
    map_placeholder.pydeck_chart(_initial_view())
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

    map_placeholder.pydeck_chart(_live_view(snapshot))
    _render_metrics(snapshot)

    time.sleep(TICK_REAL_S)
    st.rerun()
