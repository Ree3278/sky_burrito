"""Command implementations for the top-level project CLI."""

from __future__ import annotations

import subprocess

from corridor_pruning.pruning import prune_corridors
from data_processing import (
    load_buildings,
    load_residential,
    load_restaurants,
    load_street_network,
)
from settings.paths import (
    BUILDINGS_CSV,
    LANDUSE_CSV,
    RESTAURANTS_CSV,
    SIMULATION_SETUP_JSON,
    STREAMLIT_APP,
)
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
)
from settings.simulation import DEFAULT_FLEET_SIZE
from simulation.environment import (
    SimulationRuntimeConfig,
    SimulationSetupConfig,
    build_runtime_environment,
    build_simulation_setup,
    save_simulation_setup,
)
from siting_strategy import (
    fit_hubs,
    plot_building_heights,
    plot_density_maps,
    plot_supply_demand_overlay,
    plot_walk_zones,
    score_walk_zones,
    sweep_cluster_counts,
)


def validate_data_files() -> None:
    """Ensure the raw SF CSV inputs exist before running the siting pipeline."""
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
    """Run the raw-data ingest, siting, and chart-generation workflow."""
    print("=" * 60)
    print("  SKY BURRITO — HUB SITING PIPELINE")
    print("=" * 60)
    validate_data_files()

    print("\n── Step 1: Data Processing ──────────────────────────────────")
    restaurants = load_restaurants(str(RESTAURANTS_CSV))
    buildings = load_buildings(str(BUILDINGS_CSV))
    residential = load_residential(str(LANDUSE_CSV))

    print("\n  Summary:")
    print(f"    Restaurants (supply):       {len(restaurants):>6}")
    print(f"    Building obstacles:         {len(buildings):>6}")
    print(f"    Residential properties:     {len(residential):>6}")
    print(f"    Total residential units:    {residential['resunits'].sum():>6,.0f}")

    if not skip_street_network:
        print("\n── Step 2: Street Network ───────────────────────────────────")
        load_street_network()
    else:
        print("\n── Step 2: Street Network  [SKIPPED] ────────────────────────")

    print("\n── Step 3: Hub Siting (K-Means) ─────────────────────────────")
    hub_model = fit_hubs(restaurants, n_clusters=n_hubs)

    print("\n── Step 4: Walk Zone Scoring ────────────────────────────────")
    walk_scores = score_walk_zones(hub_model, restaurants, residential)

    print("\n── Step 5: Cluster Count Optimization ───────────────────────")
    sweep_cluster_counts(restaurants, residential)

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
    """Score and print the current corridor shortlist."""
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
    output_path: str = str(SIMULATION_SETUP_JSON),
) -> None:
    """Build and persist the simulation environment setup."""
    print("=" * 60)
    print("  SKY BURRITO — SIMULATION ENVIRONMENT SETUP")
    print("=" * 60)

    setup = build_simulation_setup(
        SimulationSetupConfig(
            route_count=top_n,
            sim_hour=sim_hour,
            use_automated_swap=use_automated_swap,
        )
    )
    output = save_simulation_setup(setup, output_path)
    environment = build_runtime_environment(
        setup,
        runtime_config=SimulationRuntimeConfig(
            demand_scale=demand_scale,
            fleet_size=fleet_size,
        ),
    )
    print(
        f"Simulation routes: {len(environment.routes)} | "
        f"active hubs: {len(environment.active_hub_ids)} | "
        f"fleet size: {environment.runtime_config.fleet_size} | "
        f"peak demand: {environment.network_peak_orders_per_hour:.1f}/hr"
    )
    print(f"Saved setup: {output}")


def run_simulation() -> None:
    """Launch the Streamlit digital twin."""
    if not STREAMLIT_APP.exists():
        raise FileNotFoundError(f"Missing Streamlit app: {STREAMLIT_APP}")

    cmd = ["streamlit", "run", str(STREAMLIT_APP)]
    print("Launching Streamlit simulation:")
    print(f"  {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
