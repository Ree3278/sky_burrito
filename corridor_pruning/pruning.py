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
from typing import List, Optional, TYPE_CHECKING, Dict

from .corridors import Corridor, generate_corridors
from .drone_model import estimate_drone, DroneSpec
from .ground_model import estimate_ground
from .driver_economics import DriverEconomicsSpec
from .carbon_footprint import calculate_carbon_savings
from settings.paths import BUILDINGS_CSV
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_MIN_DEMAND_WEIGHT,
    DEFAULT_MIN_TIME_DELTA_S,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
)

if TYPE_CHECKING:
    import networkx as nx

# ── Filter thresholds ────────────────────────────────────────────────────────

# Minimum time the drone must beat the car to justify the route.
# Below this the infrastructure cost isn't worth it.
MIN_TIME_DELTA_S    = DEFAULT_MIN_TIME_DELTA_S

# Minimum combined supply–demand score.
# Filters out low-traffic hub pairs that won't generate enough orders.
MIN_DEMAND_WEIGHT   = DEFAULT_MIN_DEMAND_WEIGHT

# Maximum number of corridors to keep after ranking.
TOP_N_CORRIDORS     = DEFAULT_PRUNED_CORRIDOR_COUNT


@dataclass
class ScoredCorridor:
    corridor:              Corridor
    drone_time_s:          float
    ground_time_s:         float
    time_delta_s:          float          # ground − drone  (positive = drone wins)
    drone_energy_wh:       float
    ground_energy_wh:      float
    energy_ratio:          float          # ground / drone  (>1 = drone more efficient)
    demand_weight:         int
    ground_cost_usd:       float          # What Uber pays for ground
    drone_cost_usd:        float          # What we pay for drone
    cost_arbitrage_usd:    float          # ground - drone (savings per order)
    cost_ratio:            float          # ground / drone (multiplier)
    uber_payout_breakdown: Dict[str, float]  # Detailed breakdown
    drone_co2_g:           float          # Drone CO₂ emissions (grams)
    ground_co2_g:          float          # Ground CO₂ emissions (grams)
    co2_saved_g:           float          # Reduction per delivery
    co2_reduction_pct:     float          # Percentage reduction
    composite_score:       float
    used_stubs:            bool           # True if any estimate used a fallback model


def _composite(
    time_delta_s: float,
    cost_arbitrage: float,
    energy_ratio: float,
    demand_weight: int,
) -> float:
    """
    Higher is better. Weighted composite score.
    
    Weighting: 60% cost, 20% time, 20% energy.
    (Cost is the dominant factor from the platform's perspective.)
    """
    demand_factor = math.log1p(demand_weight)
    
    time_score   = time_delta_s * demand_factor * 0.20
    cost_score   = cost_arbitrage * demand_factor * 0.60
    energy_score = energy_ratio * demand_factor * 0.20
    
    return time_score + cost_score + energy_score


def score_corridor(
    corridor: Corridor,
    drone_spec: DroneSpec = DroneSpec(),
    driver_spec: DriverEconomicsSpec = DriverEconomicsSpec(),
    G: "Optional[nx.MultiDiGraph]" = None,
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR,
) -> ScoredCorridor:
    """
    Run both models against a single Corridor and return a ScoredCorridor.

    Parameters
    ----------
    corridor : Corridor
    drone_spec : DroneSpec
        Hardware parameters. Defaults to DJI Matrice 350 RTK class.
    driver_spec : DriverEconomicsSpec
        Uber's payout formula. Defaults to Friday evening peak (hour 19).
    G : networkx.MultiDiGraph or None
        OSMnx street graph. None → stub ground model.
    sim_hour : int
        Hour (0-23) for surge pricing. Default 19 (7 PM Friday).
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
        driver_spec     = driver_spec,
        sim_hour        = sim_hour,
    )

    time_delta_s   = ground.total_time_s - drone.total_time_s
    energy_ratio   = ground.energy_wh / drone.total_energy_wh
    demand_weight  = corridor.demand_weight
    
    # Cost arbitrage
    cost_arbitrage = ground.total_cost_usd - drone.total_cost_usd
    cost_ratio     = ground.total_cost_usd / drone.total_cost_usd
    
    # Carbon footprint calculation
    # ground.road_distance_m in meters, convert to miles; 
    # ground.traffic_penalty_s in seconds, convert to hours
    ground_distance_miles = ground.road_distance_m / 1609.34
    ground_idle_hours = ground.traffic_penalty_s / 3600
    
    carbon = calculate_carbon_savings(
        drone_energy_wh=drone.total_energy_wh,
        ground_distance_miles=ground_distance_miles,
        ground_idle_time_hours=ground_idle_hours,
    )
    
    # Updated composite score with cost weighting
    score = _composite(time_delta_s, cost_arbitrage, energy_ratio, demand_weight)

    # Write results back onto the corridor object for later inspection
    corridor.drone_time_s    = drone.total_time_s
    corridor.ground_time_s   = ground.total_time_s
    corridor.road_distance_m = ground.road_distance_m
    corridor.detour_ratio    = ground.detour_ratio
    corridor.time_delta_s    = time_delta_s

    return ScoredCorridor(
        corridor              = corridor,
        drone_time_s          = drone.total_time_s,
        ground_time_s         = ground.total_time_s,
        time_delta_s          = time_delta_s,
        drone_energy_wh       = drone.total_energy_wh,
        ground_energy_wh      = ground.energy_wh,
        energy_ratio          = energy_ratio,
        demand_weight         = demand_weight,
        ground_cost_usd       = ground.total_cost_usd,
        drone_cost_usd        = drone.total_cost_usd,
        cost_arbitrage_usd    = cost_arbitrage,
        cost_ratio            = cost_ratio,
        uber_payout_breakdown = ground.uber_payout_breakdown,
        drone_co2_g           = carbon.drone_co2_g,
        ground_co2_g          = carbon.ground_co2_g,
        co2_saved_g           = carbon.co2_saved_g,
        co2_reduction_pct     = carbon.co2_reduction_pct,
        composite_score       = score,
        used_stubs            = drone.used_fallback_altitude or ground.used_stub,
    )


def prune_corridors(
    drone_spec: DroneSpec = DroneSpec(),
    driver_spec: DriverEconomicsSpec = DriverEconomicsSpec(),
    G: "Optional[nx.MultiDiGraph]" = None,
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR,
    min_time_delta_s: int  = MIN_TIME_DELTA_S,
    min_demand_weight: int = MIN_DEMAND_WEIGHT,
    top_n: int             = TOP_N_CORRIDORS,
    buildings_csv: Optional[str] = str(BUILDINGS_CSV),
) -> List[ScoredCorridor]:
    """
    Score all 132 corridors, apply filters, rank by composite score.

    Parameters
    ----------
    drone_spec : DroneSpec
    driver_spec : DriverEconomicsSpec
        Uber's payout formula. Defaults to Friday evening peak.
    G : OSMnx graph (optional, improves ground time accuracy)
    sim_hour : int
        Hour (0-23) for surge pricing. Default 19 (7 PM Friday).
    min_time_delta_s : int
        Drop routes where drone saves less than this many seconds.
    min_demand_weight : int
        Drop routes below this supply–demand product.
    top_n : int
        Return at most this many corridors.
    buildings_csv : str or None
        Path to Building_Footprints CSV. If provided, loads real obstacle heights.
        If None, uses fallback (120m assumed altitude).

    Returns
    -------
    shortlist : list of ScoredCorridor
        Sorted by composite_score descending.
    """
    corridors = generate_corridors()
    
    # Load real building obstacle heights if CSV provided
    if buildings_csv:
        try:
            from .obstacles import get_buildings_gdf, add_obstacles_to_corridors
            buildings_gdf = get_buildings_gdf(buildings_csv)
            add_obstacles_to_corridors(corridors, buildings_gdf)
        except Exception as e:
            print(f"  ⚠️  Could not load obstacles: {e}")
            print(f"     Using fallback obstacle heights (120m assumed altitude)\n")
    
    scored    = [score_corridor(c, drone_spec, driver_spec, G, sim_hour) for c in corridors]

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

    _print_summary(scored, filtered, shortlist, sim_hour)
    return shortlist


def _print_summary(
    all_scored: List[ScoredCorridor],
    filtered: List[ScoredCorridor],
    shortlist: List[ScoredCorridor],
    sim_hour: int = 19,
) -> None:
    stubs = sum(1 for s in all_scored if s.used_stubs)

    print(f"\n{'='*80}")
    print(f"  CORRIDOR PRUNING RESULTS — UBER PLATFORM ECONOMICS")
    print(f"  (Friday {sim_hour}:00)")
    print(f"{'='*80}")
    print(f"  Total corridors scored : {len(all_scored):>4}")
    print(f"  Passed all filters     : {len(filtered):>4}")
    print(f"  Final shortlist        : {len(shortlist):>4}")
    print(f"  Corridors using stubs  : {stubs:>4}")
    print(f"{'='*80}")

    if not shortlist:
        print("  ⚠  No corridors passed the filter. "
              "Try lowering min_time_delta_s or min_demand_weight.")
        return

    # Main cost comparison table
    header = f"{'Rank':<5} {'Corridor':<20} {'Uber Cost':>12} {'Drone Cost':>12} {'Savings':>12} {'Ratio':>8}"
    print(f"\n  {header}")
    print(f"  {'-'*80}")
    for rank, s in enumerate(shortlist, 1):
        stub_flag = "⚠" if s.used_stubs else "✓"
        print(
            f"  {rank:<5}"
            f" {s.corridor.label:<20}"
            f" ${s.ground_cost_usd:>11.2f}"
            f" ${s.drone_cost_usd:>11.2f}"
            f" ${s.cost_arbitrage_usd:>11.2f}"
            f" {s.cost_ratio:>7.1f}×"
        )

    # Top pick details with full breakdown
    top = shortlist[0]
    print(f"\n  Top Corridor: {top.corridor.label}")
    print(f"    Distance: {top.corridor.straight_line_m/1000:.2f} km straight line")
    print(f"    Time savings: {top.time_delta_s/60:.1f} minutes")
    print(f"    Cost savings: ${top.cost_arbitrage_usd:.2f} per delivery")
    print(f"    Carbon savings: {top.co2_saved_g/1000:.2f} kg CO₂ per delivery ({top.co2_reduction_pct:.1f}% reduction)")
    
    print(f"\n    Uber Payout Breakdown:")
    breakdown = top.uber_payout_breakdown
    print(f"      Time component:      ${breakdown['time_component']:>8.2f}  ($0.35/min)")
    print(f"      Distance component:  ${breakdown['distance_component']:>8.2f}  ($1.25/mi)")
    print(f"      Subtotal:            ${breakdown['subtotal']:>8.2f}")
    print(f"      Service fee (25%):  -${breakdown['service_fee']:>7.2f}")
    print(f"      Base pay:            ${breakdown['base_pay']:>8.2f}")
    print(f"      Surge multiplier:    {breakdown['surge_multiplier']:>8.1f}×")
    print(f"      ────────────────────────────────")
    print(f"      Total Uber pays:     ${breakdown['total_uber_payout']:>8.2f}")
    
    print(f"\n    Drone Cost & Energy Breakdown:")
    print(f"      Total energy: {top.drone_energy_wh:.1f} Wh (Climb {top.drone_energy_wh*0.3:.0f} + Cruise {top.drone_energy_wh*0.7:.0f})")
    print(f"      Battery cost (@$0.12/kWh):  ${(top.drone_energy_wh / 1000) * 0.12:>8.2f}")
    print(f"      Maintenance (@$0.016/mi):   ${(top.corridor.straight_line_m / 1609.34) * 0.016:>8.2f}")
    print(f"      ────────────────────────────────")
    print(f"      Total drone cost:    ${top.drone_cost_usd:>8.2f}")
    
    print(f"\n    Environmental Impact:")
    print(f"      Drone CO₂:     {top.drone_co2_g:>8.1f} g ({top.drone_co2_g/1000:>6.3f} kg)")
    print(f"      Ground CO₂:    {top.ground_co2_g:>8.1f} g ({top.ground_co2_g/1000:>6.3f} kg)")
    print(f"      CO₂ saved:     {top.co2_saved_g:>8.1f} g ({top.co2_saved_g/1000:>6.3f} kg) per delivery")
    print(f"      Reduction:     {top.co2_reduction_pct:>8.1f}%")
    
    print(f"{'='*80}\n")


# ── What's missing ───────────────────────────────────────────────────────────
MISSING_INPUTS = """
MISSING INPUTS — items that will materially improve filter accuracy
===================================================================


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
