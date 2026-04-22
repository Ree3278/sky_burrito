"""Shared RL observation schema for the training env and live bridge."""

from __future__ import annotations

import math
from typing import Dict, Mapping

import numpy as np

from settings.rl import (
    ACTIVE_HUBS,
    DEADHEAD_BATTERY_REQUIRED,
    QUEUE_OBSERVATION_CAP,
    TIME_ENCODING_PERIOD_HOURS,
)

ACTIVE_HUB_NAMES = list(ACTIVE_HUBS)
ACTIVE_HUB_IDS = [int(name.split()[-1]) for name in ACTIVE_HUB_NAMES]
HUB_IDX_TO_ID: Dict[int, int] = {idx: hub_id for idx, hub_id in enumerate(ACTIVE_HUB_IDS)}
HUB_ID_TO_IDX: Dict[int, int] = {hub_id: idx for idx, hub_id in HUB_IDX_TO_ID.items()}

OBSERVATION_SIZE = 42
RL_HEARTBEAT_S = 60.0


def meal_time_features(hour: float) -> np.ndarray:
    """Return the shared 4-element meal-time intensity vector."""
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


def build_observation(
    *,
    idle_by_hub: Mapping[int, float],
    queue_by_hub: Mapping[int, float],
    utilisation_by_hub: Mapping[int, float],
    fleet_size: int,
    sim_hour: float,
    battery_by_hub: Mapping[int, float] | None = None,
) -> np.ndarray:
    """Build the shared 42D observation vector."""
    if fleet_size <= 0:
        raise ValueError("fleet_size must be positive")

    observation = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
    battery_by_hub = battery_by_hub or {}

    for idx, hub_id in enumerate(ACTIVE_HUB_IDS):
        observation[idx] = float(idle_by_hub.get(hub_id, 0.0)) / float(fleet_size)
        observation[9 + idx] = min(
            float(queue_by_hub.get(hub_id, 0.0)) / float(QUEUE_OBSERVATION_CAP),
            1.0,
        )
        observation[18 + idx] = min(float(utilisation_by_hub.get(hub_id, 0.0)), 1.0)
        observation[31 + idx] = float(battery_by_hub.get(hub_id, 1.0))

    observation[27:31] = meal_time_features(sim_hour)
    observation[40] = math.sin(2 * math.pi * sim_hour / TIME_ENCODING_PERIOD_HOURS)
    observation[41] = math.cos(2 * math.pi * sim_hour / TIME_ENCODING_PERIOD_HOURS)

    return observation


__all__ = [
    "ACTIVE_HUB_IDS",
    "ACTIVE_HUB_NAMES",
    "DEADHEAD_BATTERY_REQUIRED",
    "HUB_ID_TO_IDX",
    "HUB_IDX_TO_ID",
    "OBSERVATION_SIZE",
    "RL_HEARTBEAT_S",
    "build_observation",
    "meal_time_features",
]
