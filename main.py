"""
Sky Burrito — SF Inter-District Drone Delivery Network
======================================================

Unified project CLI. Supported entrypoints:

  1. siting     — raw-data ingest, hub siting, walk-zone scoring, charts
  2. corridors  — corridor pruning and top-route report
  3. sizing     — corridor pruning + M/G/k hub sizing report
  4. simulate   — launch the Streamlit digital twin

Backwards compatibility:
  ``uv run python main.py --hubs 8`` still runs the siting pipeline.
"""

import argparse
import subprocess
import sys

from corridor_pruning.pruning import prune_corridors
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
from settings.paths import BUILDINGS_CSV, LANDUSE_CSV, RESTAURANTS_CSV, STREAMLIT_APP
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
)
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.environment import (
    SimulationEnvironmentConfig,
    build_simulation_environment,
)

ENTRYPOINTS = {"siting", "corridors", "sizing", "simulate"}


def _validate_data_files() -> None:
    missing = [
        path for path in (RESTAURANTS_CSV, BUILDINGS_CSV, LANDUSE_CSV)
        if not path.exists()
    ]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Missing required raw data files under ./data:\n"
            f"{formatted}\n"
            "Place the three SF Open Data CSVs in the data/ directory."
        )


def run_siting_pipeline(n_hubs: int = 12, skip_street_network: bool = False) -> None:
    print("=" * 60)
    print("  SKY BURRITO — HUB SITING PIPELINE")
    print("=" * 60)
    _validate_data_files()

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


def run_corridor_report(
    top_n: int = DEFAULT_PRUNED_CORRIDOR_COUNT,
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR,
) -> None:
    print("=" * 60)
    print("  SKY BURRITO — CORRIDOR PRUNING")
    print("=" * 60)

    shortlist = prune_corridors(top_n=top_n, sim_hour=sim_hour)
    print(f"\nTop {len(shortlist)} corridors at sim hour {sim_hour:02d}:00\n")

    for rank, scored in enumerate(shortlist, start=1):
        corridor = scored.corridor
        print(
            f"{rank:>2}. {corridor.label:<18} "
            f"score={scored.composite_score:>7.1f}  "
            f"savings=${scored.cost_arbitrage_usd:>5.2f}  "
            f"time={scored.time_delta_s / 60:>4.1f} min  "
            f"co2={scored.co2_reduction_pct:>5.1f}%"
        )


def run_sizing_report(
    top_n: int = DEFAULT_SIMULATION_CORRIDOR_COUNT,
    sim_hour: int = DEFAULT_CORRIDOR_SIM_HOUR,
    demand_scale: float = DEFAULT_DEMAND_SCALE,
    fleet_size: int = DEFAULT_FLEET_SIZE,
    use_automated_swap: bool = False,
) -> None:
    print("=" * 60)
    print("  SKY BURRITO — SIMULATION ENVIRONMENT SETUP")
    print("=" * 60)
    environment = build_simulation_environment(
        SimulationEnvironmentConfig(
            route_count=top_n,
            sim_hour=sim_hour,
            demand_scale=demand_scale,
            fleet_size=fleet_size,
            use_automated_swap=use_automated_swap,
        )
    )
    print(
        f"Simulation routes: {len(environment.routes)} | "
        f"active hubs: {len(environment.active_hub_ids)} | "
        f"fleet size: {environment.config.fleet_size} | "
        f"peak demand: {environment.network_peak_orders_per_hour:.1f}/hr"
    )


def run_simulation() -> None:
    if not STREAMLIT_APP.exists():
        raise FileNotFoundError(f"Missing Streamlit app: {STREAMLIT_APP}")

    cmd = ["streamlit", "run", str(STREAMLIT_APP)]
    print("Launching Streamlit simulation:")
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sky Burrito project entrypoints",
    )
    subparsers = parser.add_subparsers(dest="command")

    siting = subparsers.add_parser(
        "siting",
        help="Run raw-data ingest, hub siting, and chart generation.",
    )
    siting.add_argument(
        "--hubs",
        type=int,
        default=12,
        help="Number of launch hubs to site (default: 12)",
    )
    siting.add_argument(
        "--skip-street-network",
        action="store_true",
        help="Skip OSMnx street graph download",
    )

    corridors = subparsers.add_parser(
        "corridors",
        help="Run corridor pruning and print the top routes.",
    )
    corridors.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_PRUNED_CORRIDOR_COUNT,
        help="Number of corridors to print (default: 20)",
    )
    corridors.add_argument(
        "--sim-hour",
        type=int,
        default=DEFAULT_CORRIDOR_SIM_HOUR,
        help="Hour of day used for surge/cost modeling (default: 19)",
    )

    sizing = subparsers.add_parser(
        "sizing",
        help="Run corridor pruning and the M/G/k sizing report.",
    )
    sizing.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_SIMULATION_CORRIDOR_COUNT,
        help="Number of shortlisted corridors to use in the simulation environment (default: 10)",
    )
    sizing.add_argument(
        "--sim-hour",
        type=int,
        default=DEFAULT_CORRIDOR_SIM_HOUR,
        help="Hour of day used for surge/cost modeling (default: 19)",
    )
    sizing.add_argument(
        "--demand-scale",
        type=float,
        default=DEFAULT_DEMAND_SCALE,
        help="Scale the peak network demand before building the simulation environment",
    )
    sizing.add_argument(
        "--fleet-size",
        type=int,
        default=DEFAULT_FLEET_SIZE,
        help="Number of drones to seed into the simulation environment",
    )
    sizing.add_argument(
        "--use-automated-swap",
        action="store_true",
        help="Use the faster automated battery-swap service spec during hub sizing",
    )

    subparsers.add_parser(
        "simulate",
        help="Launch the Streamlit live digital twin.",
    )

    return parser


def cli(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Preserve the old root behavior: `python main.py --hubs 8`
    if not argv:
        argv = ["siting", *argv]
    elif argv[0] not in ENTRYPOINTS and argv[0] not in {"-h", "--help"}:
        argv = ["siting", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "siting":
        run_siting_pipeline(
            n_hubs=args.hubs,
            skip_street_network=args.skip_street_network,
        )
        return 0

    if args.command == "corridors":
        run_corridor_report(top_n=args.top_n, sim_hour=args.sim_hour)
        return 0

    if args.command == "sizing":
        run_sizing_report(
            top_n=args.top_n,
            sim_hour=args.sim_hour,
            demand_scale=args.demand_scale,
            fleet_size=args.fleet_size,
            use_automated_swap=args.use_automated_swap,
        )
        return 0

    if args.command == "simulate":
        run_simulation()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli())
