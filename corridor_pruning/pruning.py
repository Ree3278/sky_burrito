"""
Corridor pruning — filter 132 directed pairs down to the ~20 highest-value routes.

A corridor passes the filter if ALL three conditions hold:

  1. Time arbitrage:  time_delta_s >= MIN_TIME_DELTA_S
                      (drone saves at least N seconds over a car)

  2. Energy arbitrage: drone_energy_wh < ground_energy_wh
                       (flying costs less energy than idling in traffic)

  3. Demand floor:    demand_weight >= MIN_DEMAND_WEIGHT
                      (enough orders expected to justify the corridor)

Corridors are then ranked by a composite score that rewards both time savings
and commercial throughput.

Composite score
---------------
  score = time_delta_s × log1p(demand_weight) × energy_ratio

  where energy_ratio = ground_energy_wh / drone_energy_wh  (higher = better for drone)

Missing inputs that will sharpen these results
----------------------------------------------
See MISSING_INPUTS at the bottom of this file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .corridors import Corridor, generate_corridors
from .drone_model import estimate_drone, DroneSpec
from .ground_model import estimate_ground

if TYPE_CHECKING:
    import networkx as nx

# ── Filter thresholds ────────────────────────────────────────────────────────

# Minimum time the drone must beat the car to justify the route.
# Below this the infrastructure cost isn't worth it.
MIN_TIME_DELTA_S    = 120   # 2 minutes  ← tune once real traffic data arrives

# Minimum combined supply–demand score.
# Filters out low-traffic hub pairs that won't generate enough orders.
MIN_DEMAND_WEIGHT   = 100_000   # restaurants_nearby(origin) × resunits_nearby(destination)

# Maximum number of corridors to keep after ranking.
TOP_N_CORRIDORS     = 20


@dataclass
class ScoredCorridor:
    corridor:          Corridor
    drone_time_s:      float
    ground_time_s:     float
    time_delta_s:      float          # ground − drone  (positive = drone wins)
    drone_energy_wh:   float
    ground_energy_wh:  float
    energy_ratio:      float          # ground / drone  (>1 = drone more efficient)
    demand_weight:     int
    composite_score:   float
    used_stubs:        bool           # True if any estimate used a fallback model


def _composite(time_delta_s: float, demand_weight: int, energy_ratio: float) -> float:
    """Higher is better. See module docstring for formula."""
    return time_delta_s * math.log1p(demand_weight) * energy_ratio


def score_corridor(
    corridor: Corridor,
    drone_spec: DroneSpec = DroneSpec(),
    G: "Optional[nx.MultiDiGraph]" = None,
) -> ScoredCorridor:
    """
    Run both models against a single Corridor and return a ScoredCorridor.

    Parameters
    ----------
    corridor : Corridor
    drone_spec : DroneSpec
        Hardware parameters. Defaults to DJI Matrice 350 RTK class.
    G : networkx.MultiDiGraph or None
        OSMnx street graph. None → stub ground model.
    """
    drone = estimate_drone(
        straight_line_m  = corridor.straight_line_m,
        obstacle_height_m = corridor.obstacle_height_m,  # None until buildings wired in
        spec             = drone_spec,
    )

    ground = estimate_ground(
        straight_line_m = corridor.straight_line_m,
        G               = G,
        origin_lat      = corridor.origin.lat,
        origin_lon      = corridor.origin.lon,
        dest_lat        = corridor.destination.lat,
        dest_lon        = corridor.destination.lon,
    )

    time_delta_s  = ground.total_time_s - drone.total_time_s
    energy_ratio  = ground.energy_wh / drone.total_energy_wh
    demand_weight = corridor.demand_weight
    score         = _composite(time_delta_s, demand_weight, energy_ratio)

    # Write results back onto the corridor object for later inspection
    corridor.drone_time_s    = drone.total_time_s
    corridor.ground_time_s   = ground.total_time_s
    corridor.road_distance_m = ground.road_distance_m
    corridor.detour_ratio    = ground.detour_ratio
    corridor.time_delta_s    = time_delta_s

    return ScoredCorridor(
        corridor        = corridor,
        drone_time_s    = drone.total_time_s,
        ground_time_s   = ground.total_time_s,
        time_delta_s    = time_delta_s,
        drone_energy_wh = drone.total_energy_wh,
        ground_energy_wh= ground.energy_wh,
        energy_ratio    = energy_ratio,
        demand_weight   = demand_weight,
        composite_score = score,
        used_stubs      = drone.used_fallback_altitude or ground.used_stub,
    )


def prune_corridors(
    drone_spec: DroneSpec = DroneSpec(),
    G: "Optional[nx.MultiDiGraph]" = None,
    min_time_delta_s: int  = MIN_TIME_DELTA_S,
    min_demand_weight: int = MIN_DEMAND_WEIGHT,
    top_n: int             = TOP_N_CORRIDORS,
) -> List[ScoredCorridor]:
    """
    Score all 132 corridors, apply filters, rank by composite score.

    Parameters
    ----------
    drone_spec : DroneSpec
    G : OSMnx graph (optional, improves ground time accuracy)
    min_time_delta_s : int
        Drop routes where drone saves less than this many seconds.
    min_demand_weight : int
        Drop routes below this supply–demand product.
    top_n : int
        Return at most this many corridors.

    Returns
    -------
    shortlist : list of ScoredCorridor
        Sorted by composite_score descending.
    """
    corridors = generate_corridors()
    scored    = [score_corridor(c, drone_spec, G) for c in corridors]

    # Apply filters
    filtered = [
        s for s in scored
        if s.time_delta_s    >= min_time_delta_s
        and s.energy_ratio    > 1.0
        and s.demand_weight  >= min_demand_weight
    ]

    # Rank
    ranked = sorted(filtered, key=lambda s: s.composite_score, reverse=True)
    shortlist = ranked[:top_n]

    _print_summary(scored, filtered, shortlist)
    return shortlist


def _print_summary(
    all_scored: List[ScoredCorridor],
    filtered: List[ScoredCorridor],
    shortlist: List[ScoredCorridor],
) -> None:
    stubs = sum(1 for s in all_scored if s.used_stubs)

    print(f"\n{'='*72}")
    print(f"  CORRIDOR PRUNING RESULTS")
    print(f"{'='*72}")
    print(f"  Total corridors scored : {len(all_scored):>4}")
    print(f"  Passed all filters     : {len(filtered):>4}")
    print(f"  Final shortlist        : {len(shortlist):>4}")
    print(f"  Corridors using stubs  : {stubs:>4}  ⚠ see MISSING_INPUTS")
    print(f"{'='*72}")

    if not shortlist:
        print("  ⚠  No corridors passed the filter. "
              "Try lowering min_time_delta_s or min_demand_weight.")
        return

    header = f"{'Rank':<5} {'Corridor':<22} {'Δt (s)':>8} {'E-ratio':>8} {'Demand':>10} {'Score':>10} {'Stubs'}"
    print(f"\n  {header}")
    print(f"  {'-'*72}")
    for rank, s in enumerate(shortlist, 1):
        stub_flag = "⚠" if s.used_stubs else "✓"
        print(
            f"  {rank:<5}"
            f" {s.corridor.label:<22}"
            f" {s.time_delta_s:>8.0f}"
            f" {s.energy_ratio:>8.2f}×"
            f" {s.demand_weight:>10,}"
            f" {s.composite_score:>10.0f}"
            f"  {stub_flag}"
        )

    print(f"\n  Top pick: {shortlist[0].corridor.label}")
    print(f"    Drone: {shortlist[0].drone_time_s/60:.1f} min  |  "
          f"Car: {shortlist[0].ground_time_s/60:.1f} min  |  "
          f"Δt: {shortlist[0].time_delta_s/60:.1f} min saved")
    print(f"{'='*72}\n")


# ── What's missing ───────────────────────────────────────────────────────────
MISSING_INPUTS = """
MISSING INPUTS — items that will materially improve filter accuracy
===================================================================

1. Per-route obstacle heights  [CRITICAL]
   What:  Max building height directly under each of the 132 flight paths.
   Why:   Currently all corridors use ASSUMED_CRUISE_ALTITUDE_M = 120 m.
          A flat Mission→Noe route might only need 30 m; a Mission Bay→Nob Hill
          route might need 80 m. The climb cost difference is large.
   How:   Intersect each corridor's LineString with mission_noe_buildings.geojson
          using geopandas.sjoin or shapely.intersection, then take max(hgt_median_m).
   Code:  Add get_obstacle_height(hub_a, hub_b, buildings_gdf) → float
          to this package, then call it in corridors.py at generation time.

2. Real ground transit times   [HIGH]
   What:  Actual OSMnx shortest-path distances and travel times per corridor.
   Why:   The stub uses a fixed 1.55× detour factor and 30 km/h average speed.
          Some corridors (e.g., Hub 3 → Hub 10, mostly along flat Valencia St)
          will be OVER-penalised; others (e.g., Hub 1 → Hub 6 crossing a hill)
          will be UNDER-penalised.
   How:   Load G with data_processing.load_street_network(), pass to prune_corridors().
          The OSMnx block in ground_model.estimate_ground() is stubbed and ready.

3. Time-of-day traffic multiplier  [HIGH]
   What:  Hour-by-hour congestion factor for the Friday 6–9 PM rush.
   Why:   TRAFFIC_MULTIPLIER = 1.0 in ground_model.py currently applies zero
          congestion penalty. Real Friday evening speeds in the Mission can drop
          to 8–12 km/h, pushing the multiplier to 1.5–2.5×.
   How:   Options in order of effort:
          a) Uber Movement open data (free, aggregated by zone)
          b) Google Maps Routes API (time-specific travel times, paid)
          c) SFCTA SF-CHAMP model (academic, free, complex)
          Wire the multiplier into ground_model.TRAFFIC_MULTIPLIER or make it a
          callable: traffic_multiplier(hour: int, road_class: str) → float.

4. Drone hardware spec  [MEDIUM]
   What:  Confirmed mass, cruise speed, power draw for the actual drone to be used.
   Why:   drone_model.py defaults to DJI Matrice 350 RTK class values (9 kg, 15 m/s,
          350 W). A lighter platform (e.g., 5 kg, 20 m/s) would shift the energy
          crossover point and change which corridors pass the filter.
   How:   Instantiate a custom DroneSpec and pass it to prune_corridors().

5. Kiosk-to-customer walk time  [LOW — Phase 2]
   What:  The 5-minute walk assumption is uniform. Dense blocks (Union Square-style)
          have faster pedestrian throughput than hilly residential blocks.
   Why:   A corridor that "wins" on drone flight time might lose on end-to-end
          delivery time if the destination kiosk is on a steep hill.
   How:   Use the Walk Zone scores already computed in siting_strategy.walk_zones
          to weight each destination hub's "last-mile penalty."
"""
