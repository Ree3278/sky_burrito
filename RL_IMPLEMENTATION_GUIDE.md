# RL Fleet Optimization Implementation Guide

**Document Date:** April 17, 2026  
**Status:** ✅ Implementation Ready  
**Author:** GitHub Copilot + Ryan Lin

---

## 📋 Summary of Changes

This document outlines the implementation of a Reinforcement Learning (RL) system for dynamic drone fleet rebalancing across Sky Burrito's 20 viable delivery routes.

### What's New

1. **RL_FLEET_OPTIMIZATION_DESIGN.md** (Architecture & Design)
   - Complete RL system design
   - Curriculum learning strategy (Phases 1-4)
   - Reward function breakdown
   - Success metrics and KPIs

2. **simulation/rl_fleet_env.py** (Gymnasium Environment)
   - Complete gym-compatible environment
   - 42D observation space (fleet, queues, battery, meal-time, time)
   - 9D continuous action space (constrained rebalancing)
   - Multi-objective reward function
   - Time-varying demand (meal-time peaks)
   - Battery constraints for rebalancing

### Files to Create (Next Steps)

```
simulation/
├── rl_fleet_env.py           ✅ (CREATED)
├── fleet_manager.py          ⏳ (NEXT)
├── rl_fleet_agent.py         ⏳ (NEXT)
├── rl_training.py            ⏳ (NEXT)
├── rl_inference.py           ⏳ (NEXT)
└── rebalancing_policy.py     ⏳ (NEXT)

models/
├── ppo_fleet_policy_fleet10.pt   ⏳ (TRAINED)
├── ppo_fleet_policy_fleet20.pt   ⏳ (TRAINED)
├── ppo_fleet_policy_fleet30.pt   ⏳ (TRAINED)
├── ppo_fleet_policy_fleet40.pt   ⏳ (TRAINED)
└── ppo_fleet_policy_fleet50.pt   ⏳ (TRAINED)
```

---

## 🔧 Installation Requirements

### Python Packages (Add to requirements.txt)

```txt
gymnasium>=0.28.0
torch>=2.0.0
stable-baselines3>=2.0.0
tensorboard>=2.13.0
numpy>=1.24.0
scipy>=1.11.0
```

### Installation Command

```bash
pip install gymnasium torch stable-baselines3 tensorboard numpy scipy

# For GPU (CUDA 11.8+)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For GPU (Apple Silicon / MPS)
pip install torch torchvision torchaudio
# (PyTorch detects and uses Metal automatically)
```

### Verify Installation

```python
import gymnasium as gym
import torch
import numpy as np
from stable_baselines3 import PPO

print(f"Gymnasium: {gym.__version__}")
print(f"PyTorch: {torch.__version__}")
print(f"GPU Available: {torch.cuda.is_available() or torch.backends.mps.is_available()}")
```

---

## 🎯 Key Design Decisions Explained

### 1. Why Gymnasium (not Gym)?

**Reason:** Gymnasium is the actively maintained fork of OpenAI Gym
- Better API consistency
- Smaller package size
- Actively developed (gym is deprecated)

### 2. Why Continuous Actions (not Discrete)?

**Comparison:**

```
DISCRETE (600 actions):
├─ Pro: Easy to implement, simple Q-learning
├─ Con: Combinatorial explosion (10 hubs × 60 transfers)
└─ Result: Poor exploration, hard to train

CONTINUOUS (9D vector):
├─ Pro: Interpretable (one value per hub)
├─ Pro: Smooth gradient learning (PPO)
├─ Pro: Can express fine-grained decisions
└─ Result: Faster training, better policies
```

**Action Encoding:**

```python
# Each hub gets a value ∈ [-5, +5]
# Δ_i > 0: hub sends drones OUT
# Δ_i < 0: hub receives drones IN
# ∑(Δ) = 0: total fleet conserved

Example:
action = [+2, 0, -1, 0, +1, 0, -2, 0, 0]

Interpretation:
- Hub 1 sends 2 drones
- Hub 3 receives 1 drone
- Hub 6 sends 1 drone
- Hub 10 receives 2 drones
- Others: no change
```

### 3. Why 42D Observation?

```
Breakdown:
[0:9]   - Fleet distribution (normalized by fleet size)
[9:18]  - Order queues (normalized by 50)
[18:27] - Hub utilization (0-1)
[27:31] - Meal-time features (breakfast, lunch, snack, dinner)
[31:40] - Battery levels per hub
[40:42] - Cyclic time encoding (sin/cos of hour)

Total: 42D

Why:
✓ Captures fleet balance (distribution)
✓ Shows demand pressure (queues)
✓ Indicates busy hubs (utilization)
✓ Encodes demand pattern (meal times)
✓ Tracks resource constraint (battery)
✓ Captures time-of-day cycle (sin/cos)
```

### 4. Why PPO (not DDPG/SAC)?

**Algorithm Comparison:**

```
                 PPO          DDPG        SAC
────────────────────────────────────────────────
Sample Efficient ⭐⭐       ⭐⭐⭐      ⭐⭐⭐
Stability        ⭐⭐⭐      ⭐⭐       ⭐⭐⭐
Discrete Support NO          NO          NO
Continuous       ⭐⭐⭐      ⭐⭐⭐      ⭐⭐⭐
Interpretability ⭐⭐⭐      ⭐          ⭐
────────────────────────────────────────────────

Choice: PPO
├─ Works well with continuous actions
├─ Good sample efficiency (simulation is expensive)
├─ Stable training (won't diverge)
├─ Interpretable gradients
└─ Minimal hyperparameter tuning needed
```

### 5. Why Curriculum Learning (Phases 1-4)?

**Problem:** Full 10-hub network is complex
- 9 hubs to manage simultaneously
- 20 routes generating orders
- Meal-time demand variation
- Battery constraints

**Solution:** Curriculum Learning

```
Phase 1 (Easy):   Single hub (Hub 6 = sink)
                  Learn: Accumulate fleet at destination
                  Duration: 100 episodes
                  ↓
Phase 2 (Medium): Two hubs (11 ↔ 9 bidirectional)
                  Learn: Cross-hub rebalancing
                  Duration: 200 episodes
                  ↓
Phase 3 (Hard):   Full network (10 hubs, 20 routes)
                  Learn: Global optimization
                  Duration: 500 episodes
                  ↓
Phase 4 (Real):   Variable demand (meal-time peaks)
                  Learn: Adaptive strategies
                  Duration: 1000 episodes
```

### 6. Why Explore Fleet Sizes [10, 20, 30, 40, 50]?

**Rationale:** Trade-off between cost and service quality

```
Fleet Size Analysis:

Size=10:  Too small
├─ Craning (circling) frequent
├─ Unfulfilled orders high
└─ Not viable

Size=20:  Minimal
├─ Meets base demand
├─ Some peaks cause stockouts
└─ Baseline scenario

Size=30:  Optimal?
├─ Covers peaks well
├─ Good utilization
└─ Likely sweet spot

Size=40:  Over-capacity
├─ Excellent service
├─ Low utilization
├─ Higher cost
└─ May not be needed

Size=50:  Excess
├─ Always has drones ready
├─ Wasteful
└─ Poor ROI
```

**Expected Finding:**
- Size 30 likely optimal (best reward, lowest cost)
- Train all 5 to understand trade-off curve

---

## 📊 Expected Training Performance

### Phase 1 (Single Hub)

```
Episode Reward Curve:
├─ Episodes 1-20: -100 to 500 (learning exploration)
├─ Episodes 20-50: 500-2000 (rapid improvement)
├─ Episodes 50-100: Plateau at ~3000+
└─ Success: Learns to accumulate fleet at sink

Metrics:
├─ Fulfillment rate: 90%+ (no craning)
├─ Avg queue time: <2 minutes
├─ Training time: 5-10 minutes (GPU)
```

### Phase 3 (Full Network)

```
Episode Reward Curve:
├─ Episodes 1-100: Exploration, initial learning
├─ Episodes 100-300: Rapid improvement
├─ Episodes 300-500: Optimization phase
├─ Episodes 500+: Convergence

Target Metrics:
├─ Fulfillment rate: 95%+
├─ Craning frequency: <5 events/hour
├─ Dead-head percentage: <15% of fleet
├─ Training time: 2-4 hours (GPU)
```

### Phase 4 (With Meal-Time Demand)

```
Adaptive Behavior Learned:
├─ 7-9 AM: Stockpile at breakfast hub (1, 9)
├─ 11:30-1:30 PM: Concentrate at lunch hubs (6, 11)
├─ 3-5 PM: Prepare for snack (all hubs ready)
├─ 6-8 PM: Focus on dinner hubs (9, 10, 11)
├─ Off-peak: Consolidate fleet for charging
└─ Result: 98%+ fulfillment across all meal times
```

---

## 🚀 Step-by-Step Implementation

### Step 1: Install Dependencies

```bash
pip install gymnasium torch stable-baselines3 tensorboard
```

### Step 2: Test Environment

```bash
cd /Users/ryanlin/Downloads/sky_burrito
python simulation/rl_fleet_env.py
```

Expected output:
```
Testing DroneFleetEnv...
Observation shape: (42,)
Action space: Box(-5.0, 5.0, (9,), float32)
Observation space: Box(0.0, 1.0, (42,), float32)
Step 0: Reward=45.32, Hour=0.02
Step 1: Reward=38.21, Hour=0.03
...
✅ Environment test passed!
```

### Step 3: Create Training Script

Next file to implement: `simulation/rl_training.py`

Will include:
- Instantiate env + PPO agent
- Curriculum learning loop
- TensorBoard logging
- Model checkpointing
- Evaluation metrics

### Step 4: Run Training (Phase 1)

```bash
python simulation/rl_training.py --phase 1 --fleet-size 20 --gpu
```

Expected: Completes in 5-10 minutes

### Step 5: Expand to Phases 2-4

```bash
python simulation/rl_training.py --phase 3 --fleet-size 20 --gpu
```

Expected: Completes in 2-4 hours

### Step 6: Evaluate All Fleet Sizes

```bash
for size in 10 20 30 40 50; do
    python simulation/rl_training.py --phase 4 --fleet-size $size --gpu
done
```

Expected: 10-20 hours total (can run in parallel on multiple GPUs)

---

## 🔍 Key Metrics to Monitor

### Primary Metrics

```python
class TrainingMetrics:
    """
    Track during training.
    """
    
    # Fulfillment quality
    fulfillment_rate: float         # % orders fulfilled (target: >95%)
    avg_queue_wait_minutes: float   # time in queue (target: <3)
    orders_lost_daily: int          # unfulfilled (target: <5)
    
    # Operational efficiency
    craning_events_per_hour: float  # (target: <5)
    deadhead_percentage: float      # % fleet rebalancing (target: <15%)
    fleet_utilization: float        # % (target: 60-80%)
    
    # Resource usage
    avg_battery_used_percent: float # (target: 70-85%)
    rebalancing_cost_per_delivery: float  # $ (target: <$0.05)
    
    # Learning progress
    episode_reward: float           # rolling average
    reward_std: float               # stability indicator
    policy_entropy: float           # exploration level
```

### Real-Time Dashboard

Use TensorBoard:

```bash
tensorboard --logdir logs/
# Open http://localhost:6006 in browser
```

Will show:
- Episode reward curve
- Loss convergence
- Exploration metrics
- Training progress

---

## 🎓 Expected Learning Behaviors

### Phase 1 (Single Hub)

**Optimal Learned Behavior:**

```
Time-of-Day Strategy:
├─ Off-peak (midnight-7am): Consolidate at hub 0
├─ Breakfast (7-9am): No transfers (all drones ready)
├─ Mid-day (9-5pm): Balance drones at sink
├─ Evening (5-8pm): Prepare for dinner rush
└─ Night (8pm-midnight): Consolidate

Metrics:
├─ Fulfillment: 99%+ (unlimited supply)
├─ Craning: 0 (no competition)
└─ Dead-head: ~5% (minimal rebalancing)
```

### Phase 3 (Full Network)

**Optimal Learned Behavior:**

```
Hub Hierarchy (Learned):
1. High-demand hubs (9, 11, 6): Always well-stocked
2. Medium hubs (1, 2, 10): Reactive restocking
3. Low hubs (3, 5, 7): Minimal allocation

Rebalancing Strategy:
├─ Breakfast: Source → Hub 1, 9
├─ Lunch: Source → Hub 6, 11
├─ Snack: Distribute evenly
├─ Dinner: Source → Hub 9, 10, 11
├─ Off-peak: Consolidate to nearest hub

Result: 96-98% fulfillment across all hours
```

---

## ⚠️ Common Pitfalls & Solutions

### Pitfall 1: Action Not Feasible (Sum ≠ 0)

**Solution:**
```python
# Ensure conservation constraint
action_sum = np.sum(action)
if abs(action_sum) > 1e-6:
    action[0] -= action_sum  # Balance via Hub 0
```

### Pitfall 2: Craning Penalty Too Weak

**Solution:**
```python
# Increase craning penalty weight
reward -= 500 * craning_drones  # Up from 200
# Forces agent to avoid circling
```

### Pitfall 3: Dead-Head Cost Causes Starvation

**Solution:**
```python
# Balance rebalancing vs fulfillment
# If dead-head cost > fulfillment bonus:
# Agent won't rebalance even when needed

# Fix: Tune weights
reward += 100 * unfulfilled_bonus    # Strong incentive
reward -= 50 * deadhead_cost         # Weak disincentive
```

### Pitfall 4: Training Not Converging

**Solution:**
```python
# Try:
1. Reduce learning rate (3e-5 instead of 3e-4)
2. Increase batch size (256 instead of 128)
3. Longer curriculum (500 episodes per phase)
4. Better reward shaping (add intermediate bonuses)
```

---

## 📈 Success Criteria (Checkpoints)

### Phase 1 Completion

- [ ] Episode reward converges to >3000
- [ ] Fulfillment rate >99%
- [ ] Craning events = 0
- [ ] Can load and run policy

### Phase 3 Completion

- [ ] Episode reward converges to >2000
- [ ] Fulfillment rate >95%
- [ ] Craning frequency <5/hour
- [ ] Dead-head percentage <15%

### Full System (Phase 4, All Fleet Sizes)

- [ ] Fleet size 30 optimal (highest reward vs cost)
- [ ] All models trained and saved
- [ ] Metrics tracked in TensorBoard
- [ ] Documentation complete

---

## 🔗 Integration with Existing Simulation

### Current Simulation (simulation/app.py)

```python
# Current: Unlimited drone fleet
drones = [create_drone() for _ in range(1000)]  # Infinite supply

# Future: RL-optimized allocation
env = DroneFleetEnv(fleet_size=30)
obs, info = env.reset()

while not done:
    action = ppo_policy.predict(obs)[0]
    env.step(action)
    obs = get_observation()
```

### Modified Simulation Flow

```
DroneRegistry.tick()
  ├─ Generate orders (Poisson)
  ├─ RL Agent.predict(state) → action
  ├─ Execute rebalancing action
  ├─ Fulfill available orders
  └─ Update fleet metrics
```

---

## 📚 Documentation Files

### Design & Architecture

1. **RL_FLEET_OPTIMIZATION_DESIGN.md** ✅ (CREATED)
   - Complete system architecture
   - State/action/reward spaces
   - Curriculum learning plan

2. **RL_IMPLEMENTATION_GUIDE.md** (THIS FILE)
   - Step-by-step implementation
   - Installation guide
   - Common pitfalls
   - Success criteria

### Code Files

1. **simulation/rl_fleet_env.py** ✅ (CREATED)
   - Gymnasium environment
   - Observation/action generation
   - Reward calculation

2. **simulation/rl_training.py** ⏳ (NEXT)
   - PPO training loop
   - Curriculum learning
   - TensorBoard logging

3. **simulation/rl_inference.py** ⏳ (NEXT)
   - Load trained model
   - Run inference in simulation
   - A/B test vs baseline

---

## 🎯 Next Immediate Steps

1. **Install gymnasium & dependencies**
   ```bash
   pip install gymnasium torch stable-baselines3 tensorboard
   ```

2. **Test the environment**
   ```bash
   python simulation/rl_fleet_env.py
   ```

3. **Create training script**
   - Implement `simulation/rl_training.py`
   - Add curriculum learning
   - Add TensorBoard logging

4. **Run Phase 1 training**
   - Single hub, 100 episodes
   - Verify reward curve
   - Check convergence

5. **Expand to full network**
   - Phases 2-4
   - Test all fleet sizes
   - Analyze trade-offs

---

**Document Version:** 1.0  
**Status:** ✅ Guide Complete - Ready for Implementation  
**Last Updated:** April 17, 2026

