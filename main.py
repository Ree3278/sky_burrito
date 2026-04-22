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

from __future__ import annotations

import sys

from cli import (
    build_parser,
    normalize_argv,
    run_corridor_report,
    run_simulation,
    run_siting_pipeline,
    run_sizing_report,
)


def cli(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the selected command."""
    normalized_argv = normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(normalized_argv)

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
            output_path=args.output,
        )
        return 0

    if args.command == "simulate":
        run_simulation()
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(cli())
