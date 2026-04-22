"""Persistence helpers for serialized simulation setup artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from settings.paths import SIMULATION_SETUP_JSON

from .setup_models import SimulationSetup, SimulationSetupConfig


def save_simulation_setup(
    setup: SimulationSetup,
    path: str | Path = SIMULATION_SETUP_JSON,
) -> Path:
    """Persist the simulation setup JSON to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(setup.to_dict(), indent=2), encoding="utf-8")
    return path


def load_simulation_setup(
    path: str | Path = SIMULATION_SETUP_JSON,
) -> SimulationSetup:
    """Load a persisted simulation setup from disk."""
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SimulationSetup.from_dict(payload)


def load_or_build_simulation_setup(
    config: SimulationSetupConfig | None = None,
    path: str | Path = SIMULATION_SETUP_JSON,
    persist_if_built: bool = True,
) -> SimulationSetup:
    """Reuse a matching persisted setup or build a new one through the builder."""
    from .setup_builders import build_simulation_setup

    path = Path(path)
    if path.exists():
        existing = load_simulation_setup(path)
        if config is None or existing.config == config:
            return existing
        setup = build_simulation_setup(config)
        if persist_if_built:
            save_simulation_setup(setup, path)
        return setup

    setup = build_simulation_setup(config)
    if persist_if_built:
        save_simulation_setup(setup, path)
    return setup


__all__ = [
    "load_or_build_simulation_setup",
    "load_simulation_setup",
    "save_simulation_setup",
]
