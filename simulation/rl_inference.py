#!/usr/bin/env python3
"""
RL Fleet Optimization Inference Script
Load trained models and evaluate performance
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

sys.path.insert(0, str(Path(__file__).parent.parent))
from simulation.rl_fleet_env import DroneFleetEnv
from simulation.rl_training import CurriculumCallback


def load_and_evaluate(
    fleet_size: int,
    phase: int = 1,
    num_episodes: int = 5,
    checkpoint_dir: str = "models",
    verbose: bool = True,
    reward_breakdown: bool = False,
):
    """Load trained model and evaluate it"""
    
    model_path = Path(checkpoint_dir) / f"fleet_{fleet_size}" / f"ppo_fleet_{fleet_size}_phase_{phase}.zip"
    
    if not model_path.exists():
        print(f"❌ Model not found: {model_path}")
        return None
    
    if verbose:
        print(f"\nLoading model from: {model_path}")
    
    # Load model
    model = PPO.load(str(model_path))
    
    curriculum = CurriculumCallback(phase)
    cfg = curriculum.get_config()

    # Create environment that matches the phase configuration used in training
    env = DroneFleetEnv(
        fleet_size=fleet_size,
        episode_length_hours=cfg['episode_length'] / 60.0,
        sim_speedup=60,
        active_hubs=cfg['active_hubs'],
        simulation_setup=curriculum.setup,
    )
    
    # Evaluate
    if verbose:
        print(f"\nEvaluating {num_episodes} episodes...")
        print(f"Phase setup: {cfg['name']}")
        print(f"Active hubs: {', '.join(cfg['active_hubs'])}")
        print(f"Step minutes: {env.step_minutes:.2f}")
        print(f"{'Episode':<10} {'Reward':<15} {'Fulfillment':<15} {'Steps':<8}")
        print("-" * 55)
    
    total_rewards = []
    total_fulfillment = []
    total_steps = []
    episode_component_totals = []
    
    for ep in range(num_episodes):
        obs, info = env.reset()
        episode_reward = 0
        done = False
        steps = 0
        component_totals = {
            "fulfillment_bonus": 0.0,
            "queue_penalty": 0.0,
            "craning_penalty": 0.0,
            "deadhead_penalty": 0.0,
            "idle_bonus": 0.0,
            "queue_length": 0.0,
            "orders_fulfilled_this_step": 0.0,
            "deadheading_drones_this_step": 0.0,
            "idle_drones": 0.0,
        }
        
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            done = terminated or truncated
            steps += 1

            if reward_breakdown:
                components = info.get("reward_components", {})
                for key in component_totals:
                    component_totals[key] += float(components.get(key, 0.0))
        
        total_rewards.append(episode_reward)
        # FIXED: Get fulfillment rate from environment method
        fulfillment = env.get_fulfillment_rate()
        total_fulfillment.append(fulfillment)
        total_steps.append(steps)
        if reward_breakdown:
            episode_component_totals.append(component_totals)
        
        if verbose:
            fulfillment_display = f"{fulfillment:.1f}%"
            print(f"{ep+1:<10} {episode_reward:<15.2f} {fulfillment_display:<15} {steps:<8}")
    
    env.close()
    
    if verbose:
        print("-" * 55)
        avg_fulfillment_display = f"{np.mean(total_fulfillment):.1f}%"
        std_fulfillment_display = f"{np.std(total_fulfillment):.1f}%"
        print(f"{'AVERAGE':<10} {np.mean(total_rewards):<15.2f} {avg_fulfillment_display:<15} {np.mean(total_steps):<8.0f}")
        print(f"Std Dev:   {np.std(total_rewards):<15.2f} {std_fulfillment_display}")

        if reward_breakdown and episode_component_totals:
            avg_components = {
                key: float(np.mean([ep[key] for ep in episode_component_totals]))
                for key in episode_component_totals[0]
            }
            mean_steps = max(1.0, float(np.mean(total_steps)))
            print("\nReward Breakdown Per Episode")
            print(f"  Fulfillment bonus: {avg_components['fulfillment_bonus']:.2f}")
            print(f"  Queue penalty:     {avg_components['queue_penalty']:.2f}")
            print(f"  Craning penalty:   {avg_components['craning_penalty']:.2f}")
            print(f"  Deadhead penalty:  {avg_components['deadhead_penalty']:.2f}")
            print(f"  Idle bonus:        {avg_components['idle_bonus']:.2f}")
            print("\nAverage Step Drivers")
            print(f"  Queue length:      {avg_components['queue_length'] / mean_steps:.1f} orders")
            print(f"  Fulfilled / step:  {avg_components['orders_fulfilled_this_step'] / mean_steps:.1f} orders")
            print(f"  Deadheads / step:  {avg_components['deadheading_drones_this_step'] / mean_steps:.1f} drones")
            print(f"  Idle drones:       {avg_components['idle_drones'] / mean_steps:.1f} drones")
    
    result = {
        "fleet_size": fleet_size,
        "phase": phase,
        "avg_reward": np.mean(total_rewards),
        "avg_fulfillment": np.mean(total_fulfillment),
        "avg_steps": np.mean(total_steps),
        "std_reward": np.std(total_rewards),
        "std_fulfillment": np.std(total_fulfillment),
    }

    if reward_breakdown and episode_component_totals:
        result["avg_reward_components"] = {
            key: float(np.mean([ep[key] for ep in episode_component_totals]))
            for key in episode_component_totals[0]
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate trained RL models")
    parser.add_argument("--fleet-size", type=int, default=20, help="Fleet size to evaluate")
    parser.add_argument("--phase", type=int, default=1, help="Training phase")
    parser.add_argument("--num-episodes", type=int, default=5, help="Number of episodes to run")
    parser.add_argument("--checkpoint-dir", type=str, default="models", help="Model checkpoint directory")
    parser.add_argument("--all-sizes", action="store_true", help="Evaluate all fleet sizes (10-50)")
    parser.add_argument("--reward-breakdown", action="store_true",
                        help="Print average reward-component breakdown across evaluation episodes")
    
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
        result = load_and_evaluate(
            fs,
            args.phase,
            args.num_episodes,
            args.checkpoint_dir,
            verbose=True,
            reward_breakdown=args.reward_breakdown,
        )
        if result:
            results.append(result)
    
    if results:
        print(f"\n{'='*70}")
        print("SUMMARY: All Fleet Sizes")
        print(f"{'='*70}")
        print(f"{'Fleet Size':<12} {'Avg Reward':<15} {'Fulfillment %':<15} {'Std Reward':<15}")
        print("-" * 60)
        for r in results:
            fulfillment_display = f"{r['avg_fulfillment']:.1f}%"
            print(f"{r['fleet_size']:<12} {r['avg_reward']:<15.2f} {fulfillment_display:<15} {r['std_reward']:<15.2f}")
        
        best_fleet = max(results, key=lambda x: x['avg_fulfillment'])
        print(f"\n✅ Optimal fleet size: {best_fleet['fleet_size']} drones")
        print(f"   Fulfillment: {best_fleet['avg_fulfillment']:.1f}%")
        print(f"   Reward:      {best_fleet['avg_reward']:.2f}")


if __name__ == "__main__":
    main()
