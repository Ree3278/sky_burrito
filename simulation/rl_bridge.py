"""
RL Bridge — connects trained PPO agent to the live Streamlit simulation.

The trained model (DroneFleetEnv, 42D obs / 9D action) was built on instant-teleport
rebalancing semantics.  This bridge replicates those semantics exactly in the live sim:
drones are moved between hubs by manipulating FleetPool counters, not by launching
physical Drone objects.  The map shows delivery drones flying their payload arcs; the
RL rebalancing happens "behind the scenes" in the pool.

Observation layout (42D — must match DroneFleetEnv._get_observation exactly)
---------------------------------------------------------------------------
[0:9]   idle_per_hub / fleet_size          (9 active hubs)
[9:18]  queue_per_hub / 50  (clamped)      (pending orders)
[18:27] utilization_per_hub                (pads_in_use / k_pads)
[27:31] meal-time intensity                [breakfast, lunch, snack, dinner]
[31:40] battery_per_hub                    (approximated as 1.0 — not tracked live)
[40:42] time sin/cos                       (24-hour cycle)

Action layout (9D — must match DroneFleetEnv._execute_rebalancing_action)
--------------------------------------------------------------------------
action[i] ∈ [-5, +5]
  > 0 → send int(action[i]) drones FROM hub[i] TO hub[(i+1) % 9]   (cyclic)
  ≤ 0 → no-op for this hub
sum(action) balanced to 0 before execution (conservation constraint)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

import numpy as np

if TYPE_CHECKING:
    from simulation.registry import SimSnapshot
    from simulation.fleet import FleetPool


# Hub ordering must match DroneFleetEnv's ACTIVE_HUBS list exactly.
ACTIVE_HUB_IDS: List[int] = [1, 2, 3, 5, 6, 7, 9, 10, 11]   # hub .id integers
ACTIVE_HUB_NAMES: List[str] = [
    "Hub 1", "Hub 2", "Hub 3", "Hub 5", "Hub 6",
    "Hub 7", "Hub 9", "Hub 10", "Hub 11",
]
HUB_IDX_TO_ID: Dict[int, int]  = {i: hid for i, hid in enumerate(ACTIVE_HUB_IDS)}
HUB_ID_TO_IDX: Dict[int, int]  = {hid: i for i, hid in enumerate(ACTIVE_HUB_IDS)}

# Battery cost of a dead-head flight (mirrors DEADHEAD_BATTERY_REQUIRED in rl_fleet_env.py).
DEADHEAD_BATTERY_REQUIRED: Dict[str, float] = {
    "Hub 1": 0.15, "Hub 2": 0.15, "Hub 3": 0.15, "Hub 5": 0.20,
    "Hub 6": 0.15, "Hub 7": 0.20, "Hub 9": 0.15, "Hub 10": 0.20, "Hub 11": 0.15,
}

# Heartbeat: RL model fires once per simulated minute (60 s).
RL_HEARTBEAT_S: float = 60.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class RLStepResult:
    """Diagnostics from one RL heartbeat tick."""
    obs: np.ndarray                   # 42D observation that was fed to model
    action: np.ndarray                # 9D raw action from model.predict()
    moves_attempted: int              # Hub pairs where action[i] > 0
    drones_relocated: int             # Drones successfully moved
    suppressed: bool = False          # True if model is disabled this tick
    error: Optional[str] = None       # Non-None if predict() raised


# ---------------------------------------------------------------------------
# Meal-time feature helper (duplicated here to avoid importing gymnasium env)
# ---------------------------------------------------------------------------

def _meal_time_features(hour: float) -> np.ndarray:
    """
    4-element vector [breakfast, lunch, snack, dinner] ∈ [0, 1].
    Mirrors DemandGenerator.get_meal_time_features() from rl_fleet_env.py.
    """
    features = np.zeros(4, dtype=np.float32)
    if 7 <= hour < 9:
        features[0] = max(0.0, 1.0 - abs(hour - 8.0) / 1.0)
    if 11.5 <= hour < 13.5:
        features[1] = max(0.0, 1.0 - abs(hour - 12.5) / 1.0)
    if 15 <= hour < 17:
        features[2] = max(0.0, 1.0 - abs(hour - 16.0) / 1.0)
    if 18 <= hour < 20:
        features[3] = max(0.0, 1.0 - abs(hour - 19.0) / 1.0)
    return features


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class RLBridge:
    """
    Wraps a trained PPO model and translates its decisions into live-sim
    FleetPool operations.

    Parameters
    ----------
    model_path : str | Path
        Path to the .zip checkpoint, e.g.
        ``"models/fleet_20/ppo_fleet_20_phase_3.zip"``
    fleet_size : int
        Total drones in the live sim — used to normalise the observation.
    enabled : bool
        When False the bridge is a no-op (all step() calls return instantly).
    """

    def __init__(
        self,
        model_path: str | Path,
        fleet_size: int = 20,
        enabled: bool = True,
    ) -> None:
        self.fleet_size = fleet_size
        self.enabled    = enabled
        self._model     = None
        self._load_error: Optional[str] = None

        # Running episode totals (reset on each env.reset / sim restart).
        self.episode_moves: int   = 0
        self.episode_drones: int  = 0

        if enabled:
            self._load_model(Path(model_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(
        self,
        snapshot: "SimSnapshot",
        fleet:    "FleetPool",
        sim_hour: float,
    ) -> RLStepResult:
        """
        One RL heartbeat tick.

        1. Build 42D observation from the live sim snapshot.
        2. Call model.predict() to get 9D action.
        3. Apply action to FleetPool (instant-teleport rebalancing).

        Returns an RLStepResult for display in the Streamlit dashboard.
        """
        if not self.enabled or self._model is None:
            obs = self.build_observation(snapshot, sim_hour)
            return RLStepResult(obs=obs, action=np.zeros(9), moves_attempted=0,
                                drones_relocated=0, suppressed=True,
                                error=self._load_error)

        obs = self.build_observation(snapshot, sim_hour)

        try:
            action, _ = self._model.predict(obs, deterministic=True)
        except Exception as exc:
            return RLStepResult(obs=obs, action=np.zeros(9), moves_attempted=0,
                                drones_relocated=0, error=str(exc))

        moves, drones = self._apply_action(action, fleet)
        self.episode_moves  += moves
        self.episode_drones += drones

        return RLStepResult(
            obs=obs,
            action=action,
            moves_attempted=moves,
            drones_relocated=drones,
        )

    def build_observation(
        self,
        snapshot: "SimSnapshot",
        sim_hour: float,
    ) -> np.ndarray:
        """
        Build the 42D observation vector from a SimSnapshot.

        All normalisations mirror DroneFleetEnv._get_observation() exactly.
        Battery (obs[31:40]) is approximated as 1.0 — the live sim does not
        track per-drone state-of-charge.
        """
        obs = np.zeros(42, dtype=np.float32)
        fleet_snap  = snapshot.fleet        # FleetSnapshot
        hub_metrics = snapshot.hub_metrics  # Dict[int, HubMetrics]

        # [0:9]  Idle per hub, normalised by fleet size
        for idx, hub_id in enumerate(ACTIVE_HUB_IDS):
            obs[idx] = fleet_snap.idle_by_hub.get(hub_id, 0) / self.fleet_size

        # [9:18]  Queue per hub, clamped to [0, 1] (max 50 orders)
        for idx, hub_id in enumerate(ACTIVE_HUB_IDS):
            obs[9 + idx] = min(
                fleet_snap.queued_orders_by_hub.get(hub_id, 0) / 50.0, 1.0
            )

        # [18:27]  Utilisation per hub (pads in use / k_pads)
        for idx, hub_id in enumerate(ACTIVE_HUB_IDS):
            m = hub_metrics.get(hub_id)
            if m and m.k_pads > 0:
                obs[18 + idx] = min(m.pads_in_use / m.k_pads, 1.0)

        # [27:31]  Meal-time intensity features
        obs[27:31] = _meal_time_features(sim_hour)

        # [31:40]  Battery per hub — approximated as 1.0 (full charge)
        obs[31:40] = 1.0

        # [40:42]  Time encoding (24-hour sin/cos)
        obs[40] = math.sin(2 * math.pi * sim_hour / 24.0)
        obs[41] = math.cos(2 * math.pi * sim_hour / 24.0)

        return obs

    def reset_episode(self) -> None:
        """Reset per-episode counters (call when sim resets)."""
        self.episode_moves  = 0
        self.episode_drones = 0

    @property
    def is_available(self) -> bool:
        """True if the model is loaded and ready."""
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self, path: Path) -> None:
        """Load PPO model from .zip file. Sets _load_error on failure."""
        try:
            from stable_baselines3 import PPO  # lazy import — not a hard dep
        except ImportError:
            self._load_error = (
                "stable_baselines3 not installed. "
                "Run: pip install stable-baselines3"
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
        fleet:  "FleetPool",
    ) -> tuple[int, int]:
        """
        Apply 9D action to the FleetPool using instant-teleport semantics.

        Returns (moves_attempted, drones_relocated).

        Logic mirrors DroneFleetEnv._execute_rebalancing_action():
          - Clip to [-5, 5]
          - Zero-sum normalise (conservation)
          - For each hub i where action[i] > 0: move int(action[i]) drones
            from hub[i] to hub[(i+1) % 9]
        """
        action_clipped = np.clip(action, -5.0, 5.0).astype(float)

        # Enforce conservation constraint
        total = float(np.sum(action_clipped))
        if abs(total) > 1e-6:
            action_clipped[0] -= total

        moves_attempted  = 0
        drones_relocated = 0

        for i, hub_id in enumerate(ACTIVE_HUB_IDS):
            n = int(max(0.0, action_clipped[i]))
            if n <= 0:
                continue

            dest_hub_id = ACTIVE_HUB_IDS[(i + 1) % len(ACTIVE_HUB_IDS)]
            moves_attempted += 1

            for _ in range(n):
                # reserve_rebalancing_drone is an alias for checkout_drone
                if fleet.reserve_rebalancing_drone(hub_id):
                    fleet.checkin_drone(dest_hub_id)
                    drones_relocated += 1

        return moves_attempted, drones_relocated


# ---------------------------------------------------------------------------
# Module self-test (no gymnasium required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("RLBridge observation builder self-test")

    # Build a fake snapshot for testing
    from dataclasses import dataclass as _dc
    from simulation.fleet import FleetSnapshot

    @_dc
    class FakeHubMetrics:
        hub_id: int
        k_pads: int
        pads_in_use: int = 0

    @_dc
    class FakeSnapshot:
        fleet: object
        hub_metrics: dict

    fake_fleet = FleetSnapshot(
        idle_by_hub={1: 3, 2: 1, 3: 0, 5: 2, 6: 8, 7: 1, 9: 4, 10: 2, 11: 3},
        queued_orders_by_hub={1: 2, 2: 0, 3: 5, 5: 0, 6: 0, 7: 1, 9: 3, 10: 0, 11: 2},
    )
    fake_metrics = {
        hub_id: FakeHubMetrics(hub_id=hub_id, k_pads=6, pads_in_use=pads)
        for hub_id, pads in zip(ACTIVE_HUB_IDS, [3, 2, 5, 1, 4, 2, 3, 2, 3])
    }
    fake_snap = FakeSnapshot(fleet=fake_fleet, hub_metrics=fake_metrics)

    bridge = RLBridge(model_path="nonexistent.zip", fleet_size=30, enabled=False)
    obs = bridge.build_observation(fake_snap, sim_hour=19.5)
    print(f"Observation shape: {obs.shape}  (should be (42,))")
    print(f"Idle obs[0:9]:    {obs[0:9].round(3)}")
    print(f"Queue obs[9:18]:  {obs[9:18].round(3)}")
    print(f"Util obs[18:27]:  {obs[18:27].round(3)}")
    print(f"Meal obs[27:31]:  {obs[27:31].round(3)}")
    print(f"Bat  obs[31:40]:  {obs[31:40].round(3)}")
    print(f"Time obs[40:42]:  {obs[40:42].round(3)}")
    print("Self-test passed.")
