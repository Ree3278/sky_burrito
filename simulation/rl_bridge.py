"""
RL Bridge — connect the trained PPO policy to the live Streamlit simulation.

The live app keeps payload flights physical and visible on the map, while the
RL policy still uses inventory-style instant repositioning within `FleetPool`.
This preserves the trained semantics without changing public app behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from simulation.rl_schema import (
    ACTIVE_HUB_IDS,
)
from simulation.rl_schema import (
    build_observation as build_rl_observation,
)

if TYPE_CHECKING:
    from simulation.fleet import FleetPool
    from simulation.registry import SimSnapshot


@dataclass
class RLStepResult:
    """Diagnostics from a single RL heartbeat."""

    obs: np.ndarray
    action: np.ndarray
    moves_attempted: int
    drones_relocated: int
    suppressed: bool = False
    error: Optional[str] = None


class RLBridge:
    """Wrap a trained PPO model and apply its moves to the live fleet pool."""

    def __init__(
        self,
        model_path: str | Path,
        fleet_size: int = 20,
        enabled: bool = True,
    ) -> None:
        self.fleet_size = fleet_size
        self.enabled = enabled
        self._model = None
        self._load_error: Optional[str] = None

        self.episode_moves: int = 0
        self.episode_drones: int = 0

        if enabled:
            self._load_model(Path(model_path))

    def step(
        self,
        snapshot: "SimSnapshot",
        fleet: "FleetPool",
        sim_hour: float,
    ) -> RLStepResult:
        """Build an observation, predict an action, and apply rebalancing."""
        observation = self.build_observation(snapshot, sim_hour)
        if not self.enabled or self._model is None:
            return RLStepResult(
                obs=observation,
                action=np.zeros(len(ACTIVE_HUB_IDS)),
                moves_attempted=0,
                drones_relocated=0,
                suppressed=True,
                error=self._load_error,
            )

        try:
            action, _ = self._model.predict(observation, deterministic=True)
        except Exception as exc:
            return RLStepResult(
                obs=observation,
                action=np.zeros(len(ACTIVE_HUB_IDS)),
                moves_attempted=0,
                drones_relocated=0,
                error=str(exc),
            )

        moves, drones = self._apply_action(action, fleet)
        self.episode_moves += moves
        self.episode_drones += drones
        return RLStepResult(
            obs=observation,
            action=action,
            moves_attempted=moves,
            drones_relocated=drones,
        )

    def build_observation(
        self,
        snapshot: "SimSnapshot",
        sim_hour: float,
    ) -> np.ndarray:
        """Build the shared 42D observation vector for the live snapshot."""
        fleet_snapshot = snapshot.fleet
        utilisation_by_hub = {}
        for hub_id in ACTIVE_HUB_IDS:
            metrics = snapshot.hub_metrics.get(hub_id)
            if metrics is None or metrics.k_pads <= 0:
                utilisation_by_hub[hub_id] = 0.0
            else:
                utilisation_by_hub[hub_id] = metrics.pads_in_use / metrics.k_pads

        return build_rl_observation(
            idle_by_hub=fleet_snapshot.idle_by_hub,
            queue_by_hub=fleet_snapshot.queued_orders_by_hub,
            utilisation_by_hub=utilisation_by_hub,
            fleet_size=self.fleet_size,
            sim_hour=sim_hour,
        )

    def reset_episode(self) -> None:
        """Reset per-episode counters when the simulation restarts."""
        self.episode_moves = 0
        self.episode_drones = 0

    @property
    def is_available(self) -> bool:
        """True when the PPO model is loaded and callable."""
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    def _load_model(self, path: Path) -> None:
        try:
            from stable_baselines3 import PPO
        except ImportError:
            self._load_error = (
                "stable_baselines3 not installed. "
                "Run `uv sync` to install project dependencies."
            )
            return

        if not path.exists():
            self._load_error = f"Model not found: {path}"
            return

        try:
            self._model = PPO.load(str(path))
            self._load_error = None
        except Exception as exc:
            self._load_error = f"Failed to load model: {exc}"

    def _apply_action(
        self,
        action: np.ndarray,
        fleet: "FleetPool",
    ) -> tuple[int, int]:
        """
        Apply the live PPO action using demand-aware destination routing.

        Positive action on hub i means "send drones from hub i". Destinations are
        chosen dynamically from current queue pressure rather than a fixed cycle.
        """
        action_clipped = np.clip(action, -5.0, 5.0).astype(float)
        total = float(np.sum(action_clipped))
        if abs(total) > 1e-6:
            action_clipped[0] -= total

        pressure = np.array(
            [
                fleet.queued_order_count(hub_id) / (fleet.idle_count(hub_id) + 1.0)
                for hub_id in ACTIVE_HUB_IDS
            ],
            dtype=float,
        )

        moves_attempted = 0
        drones_relocated = 0

        for idx, hub_id in enumerate(ACTIVE_HUB_IDS):
            move_count = int(max(0.0, action_clipped[idx]))
            if move_count <= 0:
                continue

            destination_pressure = pressure.copy()
            destination_pressure[idx] = -1.0
            dest_idx = int(np.argmax(destination_pressure))
            if destination_pressure[dest_idx] <= 0.0:
                continue

            dest_hub_id = ACTIVE_HUB_IDS[dest_idx]
            moves_attempted += 1
            for _ in range(move_count):
                if fleet.reserve_rebalancing_drone(hub_id):
                    fleet.checkin_drone(dest_hub_id)
                    drones_relocated += 1

        return moves_attempted, drones_relocated


__all__ = ["RLBridge", "RLStepResult"]
