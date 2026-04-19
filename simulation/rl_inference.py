#!/usr/bin/env python3
"""
RL Fleet Optimization Inference Script
Load trained models and evaluate performance
"""

import sys
from pathlib import Path
import argparse
import numpy as np
from stable_baselines3 import PPO

sys.path.insert(0, str(Path(__file__).parent.parent))
from simulation.rl_fleet_env import DroneFleetEnv


def load_and_evaluate(fleet_size: int, phase: int = 1, num_episodes: int = 5, 
                      checkpoint_dir: str = "models", verbose: bool = True):
    """Load trained model and evaluate it"""
    
    model_path = Path(checkpoint_dir) / f"fleet_{fleet_size}" / f"ppo_fleet_{fleet_size}_phase_{phase}.zip"
    
    if not model_path.exists():
        print(f"❌ Model not found: {model_path}")
        return None
    
    if verbose:
        print(f"\nLoading model from: {model_path}")
    
    # Load model
    model = PPO.load(str(model_path))
    
    # Create environment
    env = DroneFleetEnv(fleet_size=fleet_size, episode_length_hours=24.0, sim_speedup=60)
    
    # Evaluate
    if verbose:
        print(f"\nEvaluating {num_episodes} episodes...")
        print(f"{'Episode':<10} {'Reward':<15} {'Fulfillment':<15} {'Steps':<8}")
        print("-" * 55)
    
    total_rewards = []
    total_fulfillment = []
    total_steps = []
    
    for ep in range(num_episodes):
        obs, info = env.reset()
        episode_reward = 0
        done = False
        steps = 0
        
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            done = terminated or truncated
            steps += 1
        
        total_rewards.append(episode_reward)
        # FIXED: Get fulfillment rate from environment method
        fulfillment = env.get_fulfillment_rate()
        total_fulfillment.append(fulfillment)
        total_steps.append(steps)
        
        if verbose:
            print(f"{ep+1:<10} {episode_reward:<15.2f} {fulfillment:<15.1f}% {steps:<8}")
    
    env.close()
    
    if verbose:
        print("-" * 55)
        print(f"{'AVERAGE':<10} {np.mean(total_rewards):<15.2f} {np.mean(total_fulfillment):<15.1f}% {np.mean(total_steps):<8.0f}")
        print(f"Std Dev:   {np.std(total_rewards):<15.2f} {np.std(total_fulfillment):<15.1f}%")
    
    return {
        "fleet_size": fleet_size,
        "phase": phase,
        "avg_reward": np.mean(total_rewards),
        "avg_fulfillment": np.mean(total_fulfillment),
        "avg_steps": np.mean(total_steps),
        "std_reward": np.std(total_rewards),
        "std_fulfillment": np.std(total_fulfillment),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate trained RL models")
    parser.add_argument("--fleet-size", type=int, default=20, help="Fleet size to evaluate")
    parser.add_argument("--phase", type=int, default=1, help="Training phase")
    parser.add_argument("--num-episodes", type=int, default=5, help="Number of episodes to run")
    parser.add_argument("--checkpoint-dir", type=str, default="models", help="Model checkpoint directory")
    parser.add_argument("--all-sizes", action="store_true", help="Evaluate all fleet sizes (10-50)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("PPO FLEET OPTIMIZATION INFERENCE")
    print("="*70)
    
    if args.all_sizes:
        fleet_sizes = [10, 20, 30, 40, 50]
    else:
        fleet_sizes = [args.fleet_size]
    
    results = []
    for fs in fleet_sizes:
        result = load_and_evaluate(fs, args.phase, args.num_episodes, args.checkpoint_dir, verbose=True)
        if result:
            results.append(result)
    
    if results:
        print(f"\n{'='*70}")
        print("SUMMARY: All Fleet Sizes")
        print(f"{'='*70}")
        print(f"{'Fleet Size':<12} {'Avg Reward':<15} {'Fulfillment %':<15} {'Std Reward':<15}")
        print("-" * 60)
        for r in results:
            print(f"{r['fleet_size']:<12} {r['avg_reward']:<15.2f} {r['avg_fulfillment']:<15.1f}% {r['std_reward']:<15.2f}")
        
        best_fleet = max(results, key=lambda x: x['avg_fulfillment'])
        print(f"\n✅ Optimal fleet size: {best_fleet['fleet_size']} drones")
        print(f"   Fulfillment: {best_fleet['avg_fulfillment']:.1f}%")
        print(f"   Reward:      {best_fleet['avg_reward']:.2f}")


if __name__ == "__main__":
    main()
