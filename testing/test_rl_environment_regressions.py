#!/usr/bin/env python3
"""Regression checks for RL environment timing and fulfillment semantics."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from simulation.rl_fleet_env import ACTIVE_HUBS, DroneFleetEnv


def test_phase_configuration_uses_requested_hubs():
    """Single-hub phases should only allocate drones to the configured hub."""
    env = DroneFleetEnv(
        fleet_size=20,
        episode_length_hours=24.0,
        sim_speedup=60.0,
        active_hubs=["Hub 6"],
    )
    env.reset(seed=42)

    hub_6_idx = ACTIVE_HUBS.index("Hub 6")
    assert env.max_timesteps == 1440, f"Expected 1440 steps, got {env.max_timesteps}"
    assert abs(env.step_minutes - 1.0) < 1e-6, f"Expected 1 minute steps, got {env.step_minutes}"
    assert env.fleet_state.idle_per_hub[hub_6_idx] == 20, "All drones should start at Hub 6 for phase 1"
    assert np.count_nonzero(env.fleet_state.idle_per_hub) == 1, "Inactive hubs should not receive drones"

    print("✓ Phase configuration activates only the requested hubs")


def test_deliveries_consume_idle_capacity_until_service_completes():
    """A drone dispatched for delivery should stay busy for the service duration."""
    env = DroneFleetEnv(
        fleet_size=3,
        episode_length_hours=1.0,
        sim_speedup=60.0,
        active_hubs=["Hub 6"],
    )
    env.reset(seed=42)

    hub_6_idx = ACTIVE_HUBS.index("Hub 6")
    env.order_queues[:] = 0
    env.order_queues[hub_6_idx] = 2
    env.episode_orders_total = 2
    env._generate_orders = lambda: None

    zero_action = np.zeros(env.action_space.shape, dtype=np.float32)

    env.step(zero_action)
    assert env.fleet_state.orders_fulfilled_this_step == 2, "Two orders should be fulfilled on the first step"
    assert env.fleet_state.idle_per_hub[hub_6_idx] == 1, "Two drones should be busy after dispatch"

    env.step(zero_action)
    assert env.fleet_state.orders_fulfilled_this_step == 0, "Per-step fulfillment counter must reset each step"
    assert env.fleet_state.idle_per_hub[hub_6_idx] == 1, "Busy drones should not return immediately"

    env.step(zero_action)
    env.step(zero_action)
    assert env.fleet_state.idle_per_hub[hub_6_idx] == 3, "Drones should return after the service duration"
    assert env.get_fulfillment_rate() == 100.0, "Fulfillment should stay at 100% for fully served demand"

    print("✓ Deliveries consume idle drones until service completes")


def test_rebalancing_stays_within_active_hubs():
    """Rebalancing should not place drones onto inactive hubs."""
    env = DroneFleetEnv(
        fleet_size=10,
        episode_length_hours=1.0,
        sim_speedup=60.0,
        active_hubs=["Hub 11", "Hub 9"],
    )
    env.reset(seed=42)

    hub_11_idx = ACTIVE_HUBS.index("Hub 11")
    hub_9_idx = ACTIVE_HUBS.index("Hub 9")
    inactive_indices = [idx for idx, hub in enumerate(ACTIVE_HUBS) if hub not in {"Hub 11", "Hub 9"}]

    action = np.zeros(env.action_space.shape, dtype=np.float32)
    action[hub_11_idx] = 1.0

    env._reset_step_counters()
    env._execute_rebalancing_action(action)
    env._sync_fleet_state()

    assert env.fleet_state.drones_deadheading == 1, "Expected one dead-heading move"
    assert env.fleet_state.idle_per_hub[hub_9_idx] >= 1, "Hub 9 should remain an active destination"
    assert np.all(env.fleet_state.idle_per_hub[inactive_indices] == 0), "Inactive hubs must stay empty"

    print("✓ Rebalancing stays within the configured active hubs")


if __name__ == "__main__":
    test_phase_configuration_uses_requested_hubs()
    test_deliveries_consume_idle_capacity_until_service_completes()
    test_rebalancing_stays_within_active_hubs()

    print("\n✅ RL environment regression checks passed!")
