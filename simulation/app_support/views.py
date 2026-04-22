"""Presentation helpers for the Streamlit simulation app."""

from __future__ import annotations

import pydeck as pdk
import streamlit as st

from simulation.layers import (
    corridor_arc_layer,
    craning_ring_layer,
    drone_layer,
    hub_label_layer,
    hub_scatter_layer,
    saturated_hub_ring_layer,
)

APP_STYLE = """
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
    font-size: 0.78rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(200, 221, 248, 0.88);
    margin-bottom: 0.25rem;
}
.featured-metric-value {
    font-size: 1.35rem;
    line-height: 1;
    font-weight: 800;
}
.route-card {
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(52, 83, 112, 0.08);
    border-radius: 20px;
    padding: 0.95rem 1rem;
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
"""


def render_header() -> None:
    """Render the page hero and legend chips."""
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


def build_initial_view(
    *,
    top_routes,
    selected_route_label: str | None,
    sizing,
    active_hubs_lookup,
    view_state: dict,
    map_style: str,
) -> pdk.Deck:
    """Build the static map shown before the simulation starts."""
    arc_layer = corridor_arc_layer(top_routes, selected_route_label)
    hub_layer = hub_scatter_layer(sizing, {}, active_hubs_lookup)
    label_layer = hub_label_layer(sizing, active_hubs_lookup)
    return pdk.Deck(
        layers=[arc_layer, hub_layer, label_layer],
        initial_view_state=pdk.ViewState(**view_state),
        map_provider="carto",
        map_style=map_style,
        tooltip={
            "html": "<b>{label}</b><br/>Δt saved: {time_delta_min} min<br/>"
            "Energy edge: {energy_ratio}×<br/>Composite score: {score}",
            "style": {"backgroundColor": "#102033", "color": "white"},
        },
    )


def build_live_view(
    *,
    snapshot,
    top_routes,
    selected_route_label: str | None,
    sizing,
    active_hubs_lookup,
    view_state: dict,
    map_style: str,
) -> pdk.Deck:
    """Build the live pydeck map using the current simulation snapshot."""
    arc_layer = corridor_arc_layer(top_routes, selected_route_label)
    hub_layer = hub_scatter_layer(sizing, snapshot.hub_metrics, active_hubs_lookup)
    label_layer = hub_label_layer(sizing, active_hubs_lookup)
    halo_layer = saturated_hub_ring_layer(sizing, snapshot.hub_metrics, active_hubs_lookup)
    return pdk.Deck(
        layers=[
            arc_layer,
            halo_layer,
            hub_layer,
            label_layer,
            drone_layer(snapshot),
            craning_ring_layer(snapshot),
        ],
        initial_view_state=pdk.ViewState(**view_state),
        map_provider="carto",
        map_style=map_style,
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


def render_featured_route(story_placeholder, *, rank, route) -> None:
    """Render the featured route card."""
    with story_placeholder.container():
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
              <p class="featured-copy">{story}</p>
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


def render_metrics(
    metrics_placeholder,
    *,
    snapshot,
    bridge,
    top_routes,
    active_hub_ids,
) -> None:
    """Render the simulation metrics and supporting route list."""
    rl_active = bridge is not None and bridge.is_available

    with metrics_placeholder.container():
        rl_badge = (
            f'<span style="color:#5bb85b;font-size:0.75rem;font-weight:700;">'
            f'● PPO active (fleet {bridge.fleet_size if bridge else "—"})</span>'
            if rl_active
            else '<span style="color:#a0aab4;font-size:0.75rem;">○ PPO off</span>'
        )
        rl_moves_label = (
            f"{snapshot.rl_drones_rebalanced} drones repositioned"
            if rl_active
            else "Enable in sidebar"
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

        if bridge and not bridge.is_available and bridge.load_error:
            st.warning(f"⚠️ RL model unavailable: {bridge.load_error}", icon="🤖")

        st.divider()
        st.markdown("**Hub pad utilisation**")
        cols = st.columns(5)
        sorted_hubs = sorted(snapshot.hub_metrics.items(), key=lambda item: -item[1].utilisation_pct)
        for index, (hub_id, metrics) in enumerate(sorted_hubs):
            col = cols[index % 5]
            icon = "🔴" if metrics.is_saturated else ("🟡" if metrics.utilisation_pct > 60 else "🟢")
            col.metric(
                f"{icon} Hub {hub_id}",
                f"{metrics.utilisation_pct:.0f}%",
                f"{metrics.pads_in_use}/{metrics.k_pads} pads  {metrics.drones_craning} craning",
                delta_color="inverse",
            )

        st.divider()
        st.markdown("**Supporting Top 10 corridor list**")
        st.caption(
            f"Demo network is limited to {len(top_routes)} top-ranked corridors across {len(active_hub_ids)} active hubs."
        )
        route_options = {route.corridor.label: route for route in top_routes}
        if route_options:
            st.selectbox(
                "Featured route on map",
                options=list(route_options.keys()),
                key="selected_route_label",
                help="Choose which top-ranked corridor is featured in the story panel and highlighted on the map.",
            )
            for rank, route in enumerate(top_routes, start=1):
                is_active = route.corridor.label == st.session_state.get("selected_route_label")
                css_class = "route-card route-card-active" if is_active else "route-card"
                st.markdown(
                    f"""
                    <div class="{css_class}">
                      <div class="route-rank">Rank #{rank}</div>
                      <div class="route-title">{route.corridor.label}</div>
                      <div class="route-meta">
                        Time saved: <strong>{route.time_delta_s / 60:.1f} min</strong><br/>
                        Savings/order: <strong>${route.cost_arbitrage_usd:.2f}</strong><br/>
                        CO₂ reduction: <strong>{route.co2_reduction_pct:.1f}%</strong>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


__all__ = [
    "APP_STYLE",
    "build_initial_view",
    "build_live_view",
    "render_featured_route",
    "render_header",
    "render_metrics",
]
