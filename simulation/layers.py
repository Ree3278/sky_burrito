"""
Pydeck layer builders.

Each function takes live simulation data and returns a configured pydeck.Layer.
Keeping layer construction out of app.py makes them testable and reusable.
"""

from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

import pydeck as pdk

from .config import (
    COLOR_CORRIDOR_ARC,
    COLOR_HUB_HEAVY, COLOR_HUB_MODERATE, COLOR_HUB_LIGHT,
    COLOR_PAD_BUSY, COLOR_PAD_FREE,
)

if TYPE_CHECKING:
    from .registry import SimSnapshot, HubMetrics
    from corridor_pruning.pruning import ScoredCorridor
    from hub_sizing.sizing import HubSizingResult


# ── Corridors ─────────────────────────────────────────────────────────────────

def corridor_arc_layer(shortlist: "List[ScoredCorridor]") -> pdk.Layer:
    """Static ArcLayer showing all active shortlisted corridors."""
    data = [
        {
            "origin_lat":  sc.corridor.origin.lat,
            "origin_lon":  sc.corridor.origin.lon,
            "dest_lat":    sc.corridor.destination.lat,
            "dest_lon":    sc.corridor.destination.lon,
            "label":       sc.corridor.label,
            "time_delta_min": round(sc.time_delta_s / 60, 1),
        }
        for sc in shortlist
    ]
    return pdk.Layer(
        "ArcLayer",
        data=data,
        get_source_position=["origin_lon", "origin_lat"],
        get_target_position=["dest_lon", "dest_lat"],
        get_source_color=COLOR_CORRIDOR_ARC,
        get_target_color=[160, 220, 255, 80],
        get_width=1.5,
        pickable=True,
        auto_highlight=True,
    )


# ── Hubs ──────────────────────────────────────────────────────────────────────

def hub_layer(
    sizing_results: "List[HubSizingResult]",
    hub_metrics: "Dict[int, HubMetrics]",
) -> pdk.Layer:
    """ScatterplotLayer for hubs, sized by k and colored by current utilisation."""
    data = []
    for r in sizing_results:
        m = hub_metrics.get(r.hub_id)
        util = m.utilisation_pct if m else 0.0
        saturated = m.is_saturated if m else False

        if r.tier == "HEAVY":
            base_color = COLOR_HUB_HEAVY
        elif r.tier == "MODERATE":
            base_color = COLOR_HUB_MODERATE
        else:
            base_color = COLOR_HUB_LIGHT

        # Pulse red when saturated
        color = COLOR_PAD_BUSY if saturated else base_color

        data.append({
            "hub_id":    r.hub_id,
            "lat":       r.service_spec and 0 or 0,   # placeholder — overridden below
            "lon":       0,
            "color":     color,
            "radius":    60 + r.k_pads * 12,
            "util_pct":  round(util, 1),
            "k_pads":    r.k_pads,
            "tier":      r.tier,
        })
    return pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.8,
        stroked=True,
        get_line_color=[255, 255, 255, 180],
        line_width_min_pixels=1,
    )


def hub_scatter_layer(
    sizing_results: "List[HubSizingResult]",
    hub_metrics: "Dict[int, HubMetrics]",
    hubs_lookup: dict,
) -> pdk.Layer:
    """
    Hub ScatterplotLayer with real coordinates injected from HUBS registry.
    """
    data = []
    for r in sizing_results:
        hub = hubs_lookup.get(r.hub_id)
        if not hub:
            continue
        m = hub_metrics.get(r.hub_id)
        saturated = m.is_saturated if m else False
        util = m.utilisation_pct if m else 0.0
        craning = m.drones_craning if m else 0

        if r.tier == "HEAVY":
            base_color = COLOR_HUB_HEAVY
        elif r.tier == "MODERATE":
            base_color = COLOR_HUB_MODERATE
        else:
            base_color = COLOR_HUB_LIGHT

        color = COLOR_PAD_BUSY if saturated else base_color

        data.append({
            "hub_id":    r.hub_id,
            "lat":       hub.lat,
            "lon":       hub.lon,
            "color":     color,
            "radius":    55 + r.k_pads * 10,
            "util_pct":  round(util, 1),
            "k_pads":    r.k_pads,
            "tier":      r.tier,
            "craning":   craning,
            "label":     f"Hub {r.hub_id}",
        })

    return pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.85,
        stroked=True,
        get_line_color=[255, 255, 255, 200],
        line_width_min_pixels=2,
    )


def hub_label_layer(sizing_results: "List[HubSizingResult]", hubs_lookup: dict) -> pdk.Layer:
    """TextLayer labelling each hub."""
    data = [
        {
            "hub_id": r.hub_id,
            "lat":    hubs_lookup[r.hub_id].lat + 0.0004,
            "lon":    hubs_lookup[r.hub_id].lon,
            "text":   f"H{r.hub_id}  {r.k_pads}▣",
        }
        for r in sizing_results if r.hub_id in hubs_lookup
    ]
    return pdk.Layer(
        "TextLayer",
        data=data,
        get_position=["lon", "lat"],
        get_text="text",
        get_size=13,
        get_color=[255, 255, 255, 220],
        get_alignment_baseline="'bottom'",
        billboard=True,
    )


# ── Drones ────────────────────────────────────────────────────────────────────

def drone_layer(snapshot: "SimSnapshot") -> pdk.Layer:
    """
    ScatterplotLayer for all active drones.
    Color encodes state; size encodes altitude (bigger = higher).
    """
    return pdk.Layer(
        "ScatterplotLayer",
        data=snapshot.drones,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius=40,
        pickable=True,
        opacity=0.9,
        stroked=False,
    )


def craning_ring_layer(snapshot: "SimSnapshot") -> pdk.Layer:
    """Pulsing ring layer highlighting drones that are craning."""
    craning = [d for d in snapshot.drones if d["state"] == "CRANING"]
    return pdk.Layer(
        "ScatterplotLayer",
        data=craning,
        get_position=["lon", "lat"],
        get_fill_color=[255, 0, 0, 0],       # transparent fill
        get_line_color=[255, 30, 30, 230],
        get_radius=80,
        stroked=True,
        filled=False,
        line_width_min_pixels=3,
        pickable=False,
    )
