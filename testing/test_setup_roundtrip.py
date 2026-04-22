"""Tests for simulation setup persistence and reconstruction."""

from __future__ import annotations

from simulation.environment import (
    SimulationSetupConfig,
    build_runtime_environment,
    build_simulation_setup,
    load_simulation_setup,
    save_simulation_setup,
)


def test_simulation_setup_roundtrip(tmp_path):
    setup = build_simulation_setup(
        SimulationSetupConfig(
            route_count=3,
            sim_hour=19,
            buildings_csv=None,
        )
    )
    path = tmp_path / "simulation_setup.json"
    save_simulation_setup(setup, path)
    loaded = load_simulation_setup(path)

    assert loaded.to_dict() == setup.to_dict()

    environment = build_runtime_environment(loaded)
    assert len(environment.routes) == len(setup.routes)
    assert set(environment.active_hub_ids) == set(setup.active_hub_ids)
