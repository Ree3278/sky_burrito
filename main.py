"""
Sky Burrito — SF Inter-District Drone Delivery Network
======================================================

Entry point for the full siting pipeline. Runs in order:

  1. Data processing   — ingest and clean the three SF Open Data CSVs
  2. Street network    — download the OSMnx ground-transit benchmark
  3. Hub siting        — K-Means cluster on restaurant density
  4. Walk zone scoring — measure residential coverage per hub
  5. Optimization      — sweep cluster counts to find optimal k
  6. Visualization     — save all analysis charts to PNG

Usage
-----
  uv run python main.py

  # Override the number of hubs:
  uv run python main.py --hubs 8

  # Skip the OSMnx download (slow, needs network):
  uv run python main.py --skip-street-network
"""

import argparse
from pathlib import Path

from data_processing import (
    load_restaurants,
    load_buildings,
    load_residential,
    load_street_network,
)
from siting_strategy import (
    fit_hubs,
    score_walk_zones,
    sweep_cluster_counts,
    plot_building_heights,
    plot_density_maps,
    plot_supply_demand_overlay,
    plot_walk_zones,
)

# ---------------------------------------------------------------------------
# Raw data file paths (relative to project root)
# ---------------------------------------------------------------------------
DATA_DIR = Path(".")

RESTAURANTS_CSV = DATA_DIR / "Registered_Business_Locations_-_San_Francisco_20260410.csv"
BUILDINGS_CSV   = DATA_DIR / "Building_Footprints_20260410.csv"
LANDUSE_CSV     = DATA_DIR / "San_Francisco_Land_Use_-_2023_20260410.csv"


def main(n_hubs: int = 12, skip_street_network: bool = False) -> None:
    print("=" * 60)
    print("  SKY BURRITO — HUB SITING PIPELINE")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Data processing
    # ------------------------------------------------------------------
    print("\n── Step 1: Data Processing ──────────────────────────────────")
    restaurants = load_restaurants(str(RESTAURANTS_CSV))
    buildings   = load_buildings(str(BUILDINGS_CSV))
    residential = load_residential(str(LANDUSE_CSV))

    print(f"\n  Summary:")
    print(f"    Restaurants (supply):       {len(restaurants):>6}")
    print(f"    Building obstacles:         {len(buildings):>6}")
    print(f"    Residential properties:     {len(residential):>6}")
    print(f"    Total residential units:    {residential['resunits'].sum():>6,.0f}")

    # ------------------------------------------------------------------
    # 2. Street network  (OSMnx, slow — requires network access)
    # ------------------------------------------------------------------
    if not skip_street_network:
        print("\n── Step 2: Street Network ───────────────────────────────────")
        G = load_street_network()
    else:
        print("\n── Step 2: Street Network  [SKIPPED] ────────────────────────")
        G = None

    # ------------------------------------------------------------------
    # 3. Hub siting
    # ------------------------------------------------------------------
    print("\n── Step 3: Hub Siting (K-Means) ─────────────────────────────")
    hub_model = fit_hubs(restaurants, n_clusters=n_hubs)

    # ------------------------------------------------------------------
    # 4. Walk zone scoring
    # ------------------------------------------------------------------
    print("\n── Step 4: Walk Zone Scoring ────────────────────────────────")
    walk_scores = score_walk_zones(hub_model, restaurants, residential)

    # ------------------------------------------------------------------
    # 5. Cluster count optimization sweep
    # ------------------------------------------------------------------
    print("\n── Step 5: Cluster Count Optimization ───────────────────────")
    sweep_cluster_counts(restaurants, residential)

    # ------------------------------------------------------------------
    # 6. Visualizations
    # ------------------------------------------------------------------
    print("\n── Step 6: Visualizations ───────────────────────────────────")
    plot_building_heights(buildings)
    plot_density_maps(restaurants, residential, buildings)
    plot_supply_demand_overlay(restaurants, residential, buildings)
    plot_walk_zones(hub_model, walk_scores, restaurants, residential, buildings)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sky Burrito hub siting pipeline")
    parser.add_argument("--hubs", type=int, default=12,
                        help="Number of launch hubs to site (default: 12)")
    parser.add_argument("--skip-street-network", action="store_true",
                        help="Skip OSMnx street graph download")
    args = parser.parse_args()
    main(n_hubs=args.hubs, skip_street_network=args.skip_street_network)
