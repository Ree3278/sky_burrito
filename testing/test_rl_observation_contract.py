"""Tests for the shared RL observation schema."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulation.fleet import FleetSnapshot
from simulation.rl_bridge import RLBridge
from simulation.rl_fleet_env import DroneFleetEnv
from simulation.rl_schema import ACTIVE_HUB_IDS, build_observation


@dataclass
class FakeHubMetrics:
    hub_id: int
    k_pads: int
    pads_in_use: int


@dataclass
class FakeSnapshot:
    fleet: FleetSnapshot
    hub_metrics: dict


def test_rl_environment_observation_uses_shared_schema():
    env = DroneFleetEnv(
        fleet_size=20,
        episode_length_hours=1.0,
        sim_speedup=60.0,
    )
    env.reset(seed=42)

    expected = build_observation(
        idle_by_hub={
            hub_id: float(env.fleet_state.idle_per_hub[idx])
            for idx, hub_id in enumerate(ACTIVE_HUB_IDS)
        },
        queue_by_hub={
            hub_id: float(env.order_queues[idx])
            for idx, hub_id in enumerate(ACTIVE_HUB_IDS)
        },
        utilisation_by_hub={
            hub_id: float(env.fleet_state.utilization_per_hub[idx])
            for idx, hub_id in enumerate(ACTIVE_HUB_IDS)
        },
        battery_by_hub={
            hub_id: float(env.fleet_state.battery_per_hub[idx])
            for idx, hub_id in enumerate(ACTIVE_HUB_IDS)
        },
        fleet_size=env.fleet_size,
        sim_hour=env.current_hour,
    )

    assert np.allclose(env._get_observation(), expected)


def test_rl_bridge_observation_uses_shared_schema():
    idle_by_hub = {hub_id: index + 1 for index, hub_id in enumerate(ACTIVE_HUB_IDS)}
    queue_by_hub = {hub_id: index for index, hub_id in enumerate(ACTIVE_HUB_IDS)}
    utilisation_by_hub = {
        hub_id: 0.1 * (index % 5)
        for index, hub_id in enumerate(ACTIVE_HUB_IDS)
    }
    battery_by_hub = {
        hub_id: 1.0 - 0.05 * index
        for index, hub_id in enumerate(ACTIVE_HUB_IDS)
    }

    snapshot = FakeSnapshot(
        fleet=FleetSnapshot(
            idle_by_hub=idle_by_hub,
            queued_orders_by_hub=queue_by_hub,
        ),
        hub_metrics={
            hub_id: FakeHubMetrics(
                hub_id=hub_id,
                k_pads=1000,
                pads_in_use=int(utilisation_by_hub[hub_id] * 1000),
            )
            for hub_id in ACTIVE_HUB_IDS
        },
    )
    bridge = RLBridge(model_path="", fleet_size=30, enabled=False)

    observed = bridge.build_observation(snapshot, sim_hour=19.5)
    expected = build_observation(
        idle_by_hub=idle_by_hub,
        queue_by_hub=queue_by_hub,
        utilisation_by_hub=utilisation_by_hub,
        battery_by_hub=battery_by_hub,
        fleet_size=30,
        sim_hour=19.5,
    )

    # The live bridge approximates battery as full charge, so compare the shared
    # parts directly and the battery segment against that live-app assumption.
    assert np.allclose(observed[:31], expected[:31], atol=1e-3)
    assert np.allclose(observed[31:40], np.ones(9))
    assert np.allclose(observed[40:42], expected[40:42], atol=1e-3)
