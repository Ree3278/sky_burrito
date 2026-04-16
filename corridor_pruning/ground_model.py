"""
Ground courier time and energy model for a single corridor.

Two modes
---------
1. OSMnx mode (accurate)
   Requires a pre-loaded NetworkX street graph G from data_processing.load_street_network().
   Computes the true shortest drivable path and applies:
     - per-edge posted speed limits
     - intersection delay at every node
     - time-of-day traffic multiplier (Friday night rush)
   ⚠ NOT YET IMPLEMENTED — needs G and a traffic dataset.

2. Stub mode (current)
   Estimates ground time from straight-line distance using:
     - an empirical detour factor (road distance ≈ 1.4× straight line for this area)
     - a conservative average urban speed
     - a fixed intersection penalty
   This is enough to rank corridors but will overestimate drone advantage on
   already-efficient straight routes.

Missing inputs
--------------
- OSMnx graph G                     → call data_processing.load_street_network()
- Time-of-day traffic multipliers   → external dataset (Google Maps, Uber Movement,
                                       or SFCTA model) keyed by hour + road class
- Per-edge speed limits             → available inside G.edges once OSMnx is loaded
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Dict

from .driver_economics import calculate_uber_payout, DriverEconomicsSpec

if TYPE_CHECKING:
    import networkx as nx

# ── Stub model parameters ────────────────────────────────────────────────────

# Average observed detour ratio for SF Mission-Noe street grid.
# Real value should come from running OSMnx on all 132 pairs.
# Reference: project notebook — "1.2 mile straight → 2.4 mile drive" = ratio 2.0
# Conservative corridor-level average is lower; using 1.55 as default.
DETOUR_FACTOR            = 1.55

# Average car speed in this corridor during off-peak (m/s).
# Friday night peak will be lower — see TRAFFIC_MULTIPLIER.
BASE_SPEED_MS            = 8.3    # ~30 km/h (18.6 mph), SF urban average

# Seconds added per signalised intersection on the path.
INTERSECTION_DELAY_S     = 12.0   # ~4 signals at 12s average wait each

# Estimated intersections per kilometre of road in this grid
INTERSECTIONS_PER_KM     = 4.0

# ⚠ MISSING: real time-of-day multiplier from traffic data.
# Friday 6–9 PM peak easily adds 40–80% to travel times in this corridor.
# Placeholder: 1.0 = no congestion adjustment.
TRAFFIC_MULTIPLIER       = 1.0    # ← REPLACE with hourly traffic data

# Car energy: litres of fuel or kWh per km (electric courier van baseline)
CAR_ENERGY_WH_PER_KM     = 200.0  # ~electric cargo bike/van at SF urban speeds


@dataclass
class GroundResult:
    road_distance_m:   float
    detour_ratio:      float
    base_travel_s:     float
    intersection_delay_s: float
    traffic_penalty_s: float
    total_time_s:      float
    energy_wh:         float
    uber_payout_breakdown: Dict[str, float]  # Output from calculate_uber_payout()
    total_cost_usd:    float                 # What we compare to drone
    used_stub:         bool        # True until OSMnx mode is implemented


def estimate_ground(
    straight_line_m: float,
    G: "Optional[nx.MultiDiGraph]" = None,
    origin_lat: float = 0.0,
    origin_lon: float = 0.0,
    dest_lat: float = 0.0,
    dest_lon: float = 0.0,
    driver_spec: DriverEconomicsSpec = DriverEconomicsSpec(),
    sim_hour: int = 19,
) -> GroundResult:
    """
    Estimate ground courier travel time, energy, and Uber payout for one corridor.

    Parameters
    ----------
    straight_line_m : float
        Haversine distance (from corridors.py).
    G : networkx.MultiDiGraph or None
        OSMnx street graph. When None, the stub model is used.
        ⚠ Pass the real graph once data_processing.load_street_network() is called.
    origin_lat, origin_lon, dest_lat, dest_lon : float
        Hub coordinates — needed for OSMnx nearest-node lookup (future use).
    driver_spec : DriverEconomicsSpec
        Uber's payout formula. Default models Friday evening peak.
    sim_hour : int
        Hour (0-23) for surge pricing. Default 19 (7 PM Friday).

    Returns
    -------
    GroundResult
    """
    if G is not None:
        # ── OSMnx mode (TODO) ────────────────────────────────────────
        # import osmnx as ox
        # orig_node = ox.nearest_nodes(G, origin_lon, origin_lat)
        # dest_node = ox.nearest_nodes(G, dest_lon, dest_lat)
        # route = ox.shortest_path(G, orig_node, dest_node, weight='travel_time')
        # ... extract road_distance_m, travel_time_s from route edges
        raise NotImplementedError(
            "OSMnx routing not yet wired up. "
            "Pass G=None to use the stub model, or implement this block."
        )

    # ── Stub model ───────────────────────────────────────────────────
    road_distance_m   = straight_line_m * DETOUR_FACTOR
    road_distance_km  = road_distance_m / 1000

    base_travel_s     = road_distance_m / BASE_SPEED_MS
    n_intersections   = road_distance_km * INTERSECTIONS_PER_KM
    intersection_s    = n_intersections * INTERSECTION_DELAY_S
    subtotal_s        = base_travel_s + intersection_s
    traffic_penalty_s = subtotal_s * (TRAFFIC_MULTIPLIER - 1.0)
    total_time_s      = subtotal_s + traffic_penalty_s

    energy_wh         = road_distance_km * CAR_ENERGY_WH_PER_KM

    # Calculate Uber payout for this route
    travel_time_minutes = total_time_s / 60
    distance_miles = road_distance_m / 1609.34
    
    uber_payout = calculate_uber_payout(
        travel_time_minutes = travel_time_minutes,
        distance_miles      = distance_miles,
        hour_of_day         = sim_hour,
        spec                = driver_spec,
    )

    return GroundResult(
        road_distance_m      = road_distance_m,
        detour_ratio         = DETOUR_FACTOR,
        base_travel_s        = base_travel_s,
        intersection_delay_s = intersection_s,
        traffic_penalty_s    = traffic_penalty_s,
        total_time_s         = total_time_s,
        energy_wh            = energy_wh,
        uber_payout_breakdown = uber_payout,
        total_cost_usd       = uber_payout['total_uber_payout'],
        used_stub            = True,
    )
