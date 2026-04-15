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
    MAP_BEARING, MAP_CENTER_LAT, MAP_CENTER_LON, MAP_STYLE, MAP_ZOOM, MAP_PITCH,
    TIME_MULTIPLIER, TICK_REAL_S,
)
from simulation.clock import SimClock
from simulation.dispatcher import Dispatcher
from simulation.registry import DroneRegistry
from simulation.layers import (
    corridor_arc_layer,
    hub_scatter_layer,
    hub_label_layer,
    saturated_hub_ring_layer,
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
    @media (max-width: 900px) {
        .sim-hero {
            display: block;
        }
        .sim-status-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
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
            bearing=MAP_BEARING,
        ),
        map_provider="carto",
        map_style=MAP_STYLE,
        tooltip={
            "html": "<b>{label}</b><br/>Δt saved: {time_delta_min} min<br/>"
                    "Hub {hub_id} — {tier} tier<br/>{k_pads} pads  util: {util_pct}%",
            "style": {"backgroundColor": "#102033", "color": "white"},
        },
    )


def _live_view(snapshot) -> pdk.Deck:
    arc_layer    = corridor_arc_layer(shortlist)
    hub_s_layer  = hub_scatter_layer(sizing, snapshot.hub_metrics, HUB_LOOKUP)
    label_layer  = hub_label_layer(sizing, HUB_LOOKUP)
    halo_layer   = saturated_hub_ring_layer(sizing, snapshot.hub_metrics, HUB_LOOKUP)
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


def _render_metrics(snapshot) -> None:
    with metrics_placeholder.container():
        st.markdown(
            f"""
            <div class="sim-status-grid">
              <div class="sim-status-card">
                <div class="sim-status-label">Sim Time</div>
                <div class="sim-status-value">{snapshot.sim_time_hhmm}</div>
                <div class="sim-status-meta">Friday peak window</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Active Drones</div>
                <div class="sim-status-value">{snapshot.total_active_drones}</div>
                <div class="sim-status-meta">{snapshot.fleet.total_idle} idle drones available</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Queued Orders</div>
                <div class="sim-status-value">{snapshot.fleet.total_queued_orders}</div>
                <div class="sim-status-meta">{snapshot.total_orders_dispatched} flights launched</div>
              </div>
              <div class="sim-status-card">
                <div class="sim-status-label">Craning Now</div>
                <div class="sim-status-value">{snapshot.total_craning}</div>
                <div class="sim-status-meta">{snapshot.total_craning_events} total craning events</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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

    with map_placeholder.container():
        st.markdown('<div class="sim-map-frame">', unsafe_allow_html=True)
        st.pydeck_chart(_live_view(snapshot))
        st.markdown("</div>", unsafe_allow_html=True)
    _render_metrics(snapshot)

    time.sleep(TICK_REAL_S)
    st.rerun()
