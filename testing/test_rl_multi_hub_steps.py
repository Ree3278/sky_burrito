#!/usr/bin/env python3
"""Quick test of multi-hub environment with RL training."""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from simulation.rl_fleet_env import DroneFleetEnv


def test_step_with_multi_hub():
    """Test that environment can execute steps with multi-hub distribution."""
    print("\n=== Testing Multi-Hub Step Execution ===")
    
    env = DroneFleetEnv(fleet_size=20, episode_length_hours=24.0, sim_speedup=10.0)
    obs, info = env.reset(seed=42)
    
    print(f"Initial observation shape: {obs.shape}")
    print(f"Initial drones per hub: {env.fleet_state.idle_per_hub}")
    
    # Execute a few steps with random actions
    for step in range(5):
        # Random action in valid range
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        
        print(f"\nStep {step + 1}:")
        print(f"  Drones per hub: {env.fleet_state.idle_per_hub}")
        print(f"  Reward: {reward:.4f}")
        print(f"  Orders fulfilled: {env.fleet_state.orders_fulfilled_this_step}")
        print(f"  Drones craning: {env.fleet_state.drones_craning}")
        print(f"  Observation shape: {obs.shape}")
        
        assert obs.shape == (42,), f"Observation shape should be (42,), got {obs.shape}"
        assert isinstance(reward, (float, np.floating)), "Reward should be float"
        
        if terminated or truncated:
            print(f"  Episode ended: terminated={terminated}, truncated={truncated}")
            break
    
    print("\n✓ Multi-hub step execution successful")


if __name__ == "__main__":
    test_step_with_multi_hub()
    print("\n✅ Multi-hub RL training test passed!")
