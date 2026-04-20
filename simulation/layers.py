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

def corridor_arc_layer(
    shortlist: "List[ScoredCorridor]",
    highlighted_label: str | None = None,
) -> pdk.Layer:
    """Static ArcLayer showing all active shortlisted corridors."""
    max_weight = max((sc.demand_weight for sc in shortlist), default=1.0)
    data = [
        {
            "origin_lat":  sc.corridor.origin.lat,
            "origin_lon":  sc.corridor.origin.lon,
            "dest_lat":    sc.corridor.destination.lat,
            "dest_lon":    sc.corridor.destination.lon,
            "label":       sc.corridor.label,
            "time_delta_min": round(sc.time_delta_s / 60, 1),
            "score":       round(sc.composite_score),
            "energy_ratio": round(sc.energy_ratio, 2),
            "width": (
                6.0 if sc.corridor.label == highlighted_label
                else 1.2 + 3.2 * (sc.demand_weight / max_weight)
            ),
            "source_color": [22, 78, 255, 220] if sc.corridor.label == highlighted_label else COLOR_CORRIDOR_ARC,
            "target_color": [255, 153, 51, 215] if sc.corridor.label == highlighted_label else [160, 220, 255, 80],
        }
        for sc in shortlist
    ]
    return pdk.Layer(
        "ArcLayer",
        data=data,
        get_source_position=["origin_lon", "origin_lat"],
        get_target_position=["dest_lon", "dest_lat"],
        get_source_color="source_color",
        get_target_color="target_color",
        get_width="width",
        pickable=True,
        auto_highlight=True,
        great_circle=True,
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
            "line_color": [255, 255, 255, 235] if saturated else [24, 34, 48, 210],
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
        opacity=0.92,
        stroked=True,
        get_line_color="line_color",
        line_width_min_pixels=2.5,
    )


def hub_label_layer(sizing_results: "List[HubSizingResult]", hubs_lookup: dict) -> pdk.Layer:
    """TextLayer labelling each hub."""
    data = [
        {
            "hub_id": r.hub_id,
            "lat":    hubs_lookup[r.hub_id].lat + 0.0004,
            "lon":    hubs_lookup[r.hub_id].lon,
            "text":   f"Hub {r.hub_id}\n{r.k_pads} pads",
        }
        for r in sizing_results if r.hub_id in hubs_lookup
    ]
    return pdk.Layer(
        "TextLayer",
        data=data,
        get_position=["lon", "lat"],
        get_text="text",
        get_size=13,
        get_color=[22, 32, 44, 235],
        get_alignment_baseline="'bottom'",
        get_text_anchor="'middle'",
        billboard=True,
        get_background_color=[255, 255, 255, 185],
        background=True,
    )


def saturated_hub_ring_layer(
    sizing_results: "List[HubSizingResult]",
    hub_metrics: "Dict[int, HubMetrics]",
    hubs_lookup: dict,
) -> pdk.Layer:
    """Halo layer for hubs that are currently saturated."""
    data = []
    for r in sizing_results:
        hub = hubs_lookup.get(r.hub_id)
        m = hub_metrics.get(r.hub_id)
        if not hub or not m or not m.is_saturated:
            continue
        data.append(
            {
                "lat": hub.lat,
                "lon": hub.lon,
                "radius": 95 + r.k_pads * 12,
            }
        )

    return pdk.Layer(
        "ScatterplotLayer",
        data=data,
        get_position=["lon", "lat"],
        get_fill_color=[255, 30, 30, 24],
        get_line_color=[255, 60, 60, 210],
        get_radius="radius",
        stroked=True,
        filled=True,
        line_width_min_pixels=3,
        pickable=False,
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
        get_radius=44,
        pickable=True,
        opacity=0.94,
        stroked=True,
        get_line_color=[255, 255, 255, 120],
        line_width_min_pixels=1,
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
        get_radius=95,
        stroked=True,
        filled=False,
        line_width_min_pixels=3,
        pickable=False,
    )
