"""Argument parser helpers for the top-level project CLI."""

from __future__ import annotations

import argparse

from settings.paths import SIMULATION_SETUP_JSON
from settings.pipeline import (
    DEFAULT_CORRIDOR_SIM_HOUR,
    DEFAULT_DEMAND_SCALE,
    DEFAULT_PRUNED_CORRIDOR_COUNT,
    DEFAULT_SIMULATION_CORRIDOR_COUNT,
)
from settings.simulation import DEFAULT_FLEET_SIZE

ENTRYPOINTS = {"siting", "corridors", "sizing", "simulate"}


def build_parser() -> argparse.ArgumentParser:
    """Build the project CLI argument parser."""
    parser = argparse.ArgumentParser(description="Sky Burrito project entrypoints")
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
    sizing.add_argument(
        "--output",
        type=str,
        default=str(SIMULATION_SETUP_JSON),
        help="Path to the persisted simulation setup JSON",
    )

    subparsers.add_parser(
        "simulate",
        help="Launch the Streamlit live digital twin.",
    )

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    """Preserve the historical CLI behavior of defaulting to `siting`."""
    if not argv:
        return ["siting"]
    if argv[0] not in ENTRYPOINTS and argv[0] not in {"-h", "--help"}:
        return ["siting", *argv]
    return argv
