#!/usr/bin/env python3
"""
RL Fleet Optimization Training Script
Uses PPO (Proximal Policy Optimization) with Stable-Baselines3
Implements 4-phase curriculum learning for drone fleet management
"""

import os
import sys
import argparse
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.utils import FloatSchedule
from stable_baselines3.common.vec_env import DummyVecEnv
import tensorboard

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.rl_fleet_env import DroneFleetEnv


class CurriculumCallback:
    """Manages curriculum learning phases"""
    
    def __init__(self, phase: int = 1):
        self.phase = phase
        self.phase_config = self._get_phase_config(phase)
    
    def _get_phase_config(self, phase: int) -> dict:
        """Get configuration for each curriculum phase"""
        configs = {
            1: {  # Single hub - easiest
                "name": "Single Hub (Hub 6 only)",
                "active_hubs": ["Hub 6"],
                "routes": 5,
                "episode_length": 360,  # 6 hours
                "timesteps": 50_000,
                "learning_rate": 1e-3,
                "n_steps": 2048,
                "batch_size": 64,
                "n_epochs": 20,
            },
            2: {  # Two-hub bidirectional
                "name": "Two Hubs Bidirectional (Hub 11 ↔ Hub 9)",
                "active_hubs": ["Hub 11", "Hub 9"],
                "routes": 2,
                "episode_length": 720,  # 12 hours
                "timesteps": 100_000,
                "learning_rate": 5e-4,
                "n_steps": 2048,
                "batch_size": 128,
                "n_epochs": 20,
            },
            3: {  # Full network
                "name": "Full Network (9 hubs, 20 routes)",
                "active_hubs": [
                    "Hub 1", "Hub 2", "Hub 3", "Hub 5", "Hub 6",
                    "Hub 7", "Hub 9", "Hub 10", "Hub 11"
                ],
                "routes": 20,
                "episode_length": 1440,  # 24 hours
                "timesteps": 500_000,
                "learning_rate": 3e-4,
                "n_steps": 2048,
                "batch_size": 256,
                "n_epochs": 20,
            },
            4: {  # Full network with meal-time peaks
                "name": "Full Network with Meal-Time Peaks",
                "active_hubs": [
                    "Hub 1", "Hub 2", "Hub 3", "Hub 5", "Hub 6",
                    "Hub 7", "Hub 9", "Hub 10", "Hub 11"
                ],
                "routes": 20,
                "episode_length": 1440,  # 24 hours
                "timesteps": 1_000_000,
                "learning_rate": 2e-4,
                "n_steps": 2048,
                "batch_size": 256,
                "n_epochs": 20,
            },
        }
        return configs.get(phase, configs[1])
    
    def get_config(self) -> dict:
        return self.phase_config
    
    def info(self):
        """Print phase information"""
        cfg = self.phase_config
        print(f"\n{'='*70}")
        print(f"PHASE {self.phase}: {cfg['name']}")
        print(f"{'='*70}")
        print(f"Active hubs:        {len(cfg['active_hubs'])} hubs")
        print(f"Routes:             {cfg['routes']} viable routes")
        print(f"Episode length:     {cfg['episode_length']} minutes (steps)")
        print(f"Training timesteps: {cfg['timesteps']:,}")
        print(f"Learning rate:      {cfg['learning_rate']:.2e}")
        print(f"Batch size:         {cfg['batch_size']}")
        print(f"Update epochs:      {cfg['n_epochs']}")
        print(f"{'='*70}\n")


def create_environment(fleet_size: int, phase: int = 1, curriculum: CurriculumCallback = None) -> DroneFleetEnv:
    """Create RL environment with phase-specific configuration"""
    if curriculum is None:
        curriculum = CurriculumCallback(phase)
    
    cfg = curriculum.get_config()
    
    # Convert minutes to hours for episode_length_hours
    episode_hours = cfg['episode_length'] / 60.0
    
    env = DroneFleetEnv(
        fleet_size=fleet_size,
        episode_length_hours=episode_hours,
        sim_speedup=60,  # 1 minute per step
        active_hubs=cfg['active_hubs'],
    )
    
    return env


def train_fleet_size(
    fleet_size: int,
    phase: int = 1,
    gpu: bool = True,
    checkpoint_dir: str = "models",
    timesteps_override: int | None = None,
    resume_from: str | None = None,
    learning_rate_override: float | None = None,
):
    """Train PPO agent for a specific fleet size"""
    
    curriculum = CurriculumCallback(phase)
    cfg = curriculum.get_config()
    
    # Print phase info
    curriculum.info()
    
    # Create environment
    print(f"Creating environment for fleet size: {fleet_size} drones...")
    env = create_environment(fleet_size, phase, curriculum)
    print(f"✓ Environment created")
    print(f"  Observation space: {env.observation_space.shape}")
    print(f"  Action space:      {env.action_space.shape}")
    print(f"  Episode length:    {cfg['episode_length']} steps")
    
    # Determine device
    if gpu:
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    else:
        device = "cpu"
    device = 'cpu'
    
    print(f"  Device:            {device}")

    total_timesteps = timesteps_override if timesteps_override is not None else cfg['timesteps']
    if total_timesteps <= 0:
        raise ValueError("timesteps_override must be positive")
    learning_rate = learning_rate_override if learning_rate_override is not None else cfg['learning_rate']
    if learning_rate <= 0:
        raise ValueError("learning_rate_override must be positive")
    
    # Create checkpoint directory
    checkpoint_path = Path(checkpoint_dir) / f"fleet_{fleet_size}"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    logs_path = Path("logs") / f"fleet_{fleet_size}_phase_{phase}"
    logs_path.mkdir(parents=True, exist_ok=True)
    
    # Create model name
    model_name = f"ppo_fleet_{fleet_size}_phase_{phase}"
    model_path = checkpoint_path / model_name
    
    print(f"\nInitializing PPO agent...")
    print(f"  Checkpoint path:   {checkpoint_path}")
    print(f"  Logs path:         {logs_path}")
    print(f"  Learning rate:     {learning_rate:.2e}")

    # Create PPO agent or resume from an existing checkpoint
    if resume_from is not None:
        resume_path = Path(resume_from)
        if not resume_path.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {resume_path}")

        print(f"  Resume checkpoint: {resume_path}")
        model = PPO.load(str(resume_path), env=env, device=device)
        model.tensorboard_log = str(logs_path)
        model.learning_rate = learning_rate
        model.lr_schedule = FloatSchedule(learning_rate)
        print(f"✓ PPO agent loaded with {sum(p.numel() for p in model.policy.parameters()):,} parameters")
    else:
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=learning_rate,
            n_steps=cfg['n_steps'],
            batch_size=cfg['batch_size'],
            n_epochs=cfg['n_epochs'],
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            verbose=1,
            tensorboard_log=str(logs_path),
            device=device,
        )
        print(f"✓ PPO agent created with {sum(p.numel() for p in model.policy.parameters()):,} parameters")
    
    # Create callbacks
    checkpoint_callback = CheckpointCallback(
        save_freq=max(1000, total_timesteps // 10),
        save_path=str(checkpoint_path),
        name_prefix=f"ppo_fleet_{fleet_size}_phase_{phase}_checkpoint",
    )
    
    # Train the model
    print(f"\nStarting training...")
    print(f"  Total timesteps: {total_timesteps:,}")
    print(f"  Expected time:   {total_timesteps / 50_000:.1f}x Phase 1 duration")
    print(f"\nOpen TensorBoard with:")
    print(f"  tensorboard --logdir {logs_path.parent}")
    
    try:
        model.learn(
            total_timesteps=total_timesteps,
            callback=checkpoint_callback,
            reset_num_timesteps=resume_from is None,
            progress_bar=True,
        )
    except KeyboardInterrupt:
        print("\n⚠️  Training interrupted by user")
    
    # Save final model
    model.save(str(model_path))
    print(f"\n✓ Model saved to {model_path}.zip")
    
    # Test the trained model
    print(f"\nTesting trained model...")
    test_reward = evaluate_model(model, env, num_episodes=3)
    print(f"✓ Average test reward: {test_reward:.2f}")
    
    env.close()
    
    return str(model_path)


def evaluate_model(model: PPO, env: DroneFleetEnv, num_episodes: int = 3) -> float:
    """Evaluate a trained model"""
    
    total_rewards = []
    
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
        print(
            f"  Episode {ep+1}: Reward={episode_reward:.2f}, "
            f"Steps={steps}, Fulfillment={info.get('fulfillment_rate', 0):.1f}%"
        )
    
    return np.mean(total_rewards)


def main():
    parser = argparse.ArgumentParser(description="Train PPO agent for drone fleet optimization")
    
    parser.add_argument("--phase", type=int, default=1, choices=[1, 2, 3, 4],
                       help="Curriculum learning phase (1=single hub, 4=full network with peaks)")
    parser.add_argument("--fleet-sizes", type=int, nargs="+", default=[20],
                       help="Fleet sizes to train (e.g., 10 20 30 40 50)")
    parser.add_argument("--no-gpu", action="store_true", help="Disable GPU training")
    parser.add_argument("--checkpoint-dir", type=str, default="models",
                       help="Directory to save model checkpoints")
    parser.add_argument("--timesteps", type=int, default=None,
                       help="Override the default training timesteps for the selected phase")
    parser.add_argument("--resume-from", type=str, default=None,
                       help="Path to an existing .zip checkpoint to continue training from")
    parser.add_argument("--learning-rate", type=float, default=None,
                       help="Override the default learning rate for new or resumed training")
    parser.add_argument("--test-only", action="store_true", help="Test environment without training")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("PPO FLEET OPTIMIZATION TRAINING")
    print("="*70)
    
    if args.test_only:
        print("\n[TEST MODE] Testing environment without training...")
        env = create_environment(fleet_size=20, phase=1)
        obs, info = env.reset()
        for _ in range(10):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
        print("✓ Environment test passed")
        env.close()
        return
    
    # Train each fleet size
    for fleet_size in args.fleet_sizes:
        print(f"\n{'#'*70}")
        print(f"# Training Fleet Size: {fleet_size} drones")
        print(f"{'#'*70}")
        
        try:
            model_path = train_fleet_size(
                fleet_size=fleet_size,
                phase=args.phase,
                gpu=not args.no_gpu,
                checkpoint_dir=args.checkpoint_dir,
                timesteps_override=args.timesteps,
                resume_from=args.resume_from,
                learning_rate_override=args.learning_rate,
            )
            print(f"\n✅ Successfully trained fleet size {fleet_size}")
            print(f"   Model saved to: {model_path}.zip")
            
        except Exception as e:
            print(f"\n❌ Error training fleet size {fleet_size}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("TRAINING COMPLETE")
    print(f"{'='*70}")
    print("\nNext steps:")
    print("1. Monitor training with TensorBoard:")
    print(f"   tensorboard --logdir logs")
    print("\n2. Evaluate models:")
    print(f"   python simulation/rl_inference.py --fleet-size 20 --phase {args.phase}")
    print("\n3. Deploy to simulation:")
    print(f"   python simulation/app.py --use-rl --fleet-size 20")


if __name__ == "__main__":
    main()
