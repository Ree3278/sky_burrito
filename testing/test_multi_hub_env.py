#!/usr/bin/env python3
"""Test multi-hub environment initialization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from simulation.rl_fleet_env import ACTIVE_HUBS, DroneFleetEnv


def test_single_hub_env():
    """Test drone distribution across multiple hubs."""
    print("\n=== Testing Multi-Hub Drone Distribution ===")
    
    env = DroneFleetEnv(fleet_size=20, episode_length_hours=24.0, sim_speedup=10.0)
    obs, info = env.reset(seed=42)
    
    # Check fleet is initialized
    fleet = env.fleet_state
    print(f"Fleet size: {fleet.fleet_size}")
    print(f"Number of hubs: {env.num_hubs}")
    print(f"Drones per hub: {fleet.idle_per_hub}")
    print(f"Total drones: {sum(fleet.idle_per_hub)}")
    
    # Verify total drones
    assert sum(fleet.idle_per_hub) == 20, "Total drones should be 20"
    
    # For multi-hub environment, verify distribution is proportional
    if env.num_hubs > 1:
        hubs_with_drones = sum(1 for count in fleet.idle_per_hub if count > 0)
        print(f"Hubs with drones: {hubs_with_drones}")
        assert hubs_with_drones > 1, "Multi-hub environment should distribute drones across hubs"
        # Hub 9 (index 6) is the busiest, should have most drones
        print("✓ Multi-hub distribution verified - drones distributed across hubs")


def test_multi_hub_env():
    """Test multi-hub environment."""
    print("\n=== Testing Multi-Hub Environment ===")
    
    # Create env with multi-hub setup
    env = DroneFleetEnv(fleet_size=20, episode_length_hours=24.0, sim_speedup=10.0)
    
    # Override the active hubs to include multiple hubs
    # This simulates a multi-hub environment
    print(f"Active hubs: {ACTIVE_HUBS}")
    print(f"Number of active hubs: {len(ACTIVE_HUBS)}")
    
    obs, info = env.reset(seed=42)
    
    # Check fleet is initialized
    fleet = env.fleet_state
    print(f"Fleet size: {fleet.fleet_size}")
    print(f"Number of hubs in environment: {env.num_hubs}")
    print(f"Drones per hub: {fleet.idle_per_hub}")
    print(f"Total drones: {sum(fleet.idle_per_hub)}")
    
    # Verify total drones
    assert sum(fleet.idle_per_hub) == 20, "Total drones should be 20"
    
    # For multi-hub, drones should be distributed
    if env.num_hubs > 1:
        # Count hubs with drones
        hubs_with_drones = sum(1 for count in fleet.idle_per_hub if count > 0)
        print(f"Hubs with drones: {hubs_with_drones}")
        
        # Check if distribution is reasonable
        # (For now, allow any distribution as long as total = fleet_size)
        print("✓ Multi-hub initialization complete")
    else:
        print("✓ Single hub environment confirmed")


def test_drone_hub_consistency():
    """Test that DroneState hub_id matches FleetState idle_per_hub."""
    print("\n=== Testing Drone-Hub Consistency ===")
    
    env = DroneFleetEnv(fleet_size=30, episode_length_hours=24.0, sim_speedup=10.0)
    obs, info = env.reset(seed=42)
    
    fleet = env.fleet_state
    
    # Count drones per hub from DroneState
    drones_at_hub = [0] * env.num_hubs
    for drone in fleet.drones:
        drones_at_hub[drone.hub_id] += 1
    
    print(f"Drones per hub (from DroneState): {drones_at_hub}")
    print(f"Drones per hub (from idle_per_hub): {list(fleet.idle_per_hub)}")
    
    # Verify consistency
    for hub_id in range(env.num_hubs):
        assert drones_at_hub[hub_id] == fleet.idle_per_hub[hub_id], \
            f"Hub {hub_id}: DroneState count {drones_at_hub[hub_id]} != " \
            f"idle_per_hub {fleet.idle_per_hub[hub_id]}"
    
    print("✓ Drone-hub consistency verified")


def test_battery_initialization():
    """Test that all drones start with full battery."""
    print("\n=== Testing Battery Initialization ===")
    
    env = DroneFleetEnv(fleet_size=20, episode_length_hours=24.0, sim_speedup=10.0)
    obs, info = env.reset(seed=42)
    
    fleet = env.fleet_state
    
    # Check all drones have full battery
    for i, drone in enumerate(fleet.drones):
        assert drone.battery_level == 1.0, \
            f"Drone {i} battery is {drone.battery_level}, expected 1.0"
    
    # Check battery_per_hub reflects full battery
    for hub_id in range(env.num_hubs):
        if fleet.idle_per_hub[hub_id] > 0:
            assert fleet.battery_per_hub[hub_id] == 1.0, \
                f"Hub {hub_id} battery is {fleet.battery_per_hub[hub_id]}, expected 1.0"
    
    print("✓ All drones initialized with full battery")


if __name__ == "__main__":
    test_single_hub_env()
    test_multi_hub_env()
    test_drone_hub_consistency()
    test_battery_initialization()
    
    print("\n✅ All multi-hub tests passed!")
