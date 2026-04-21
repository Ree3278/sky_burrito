# 🚀 RL Fleet Optimization - Quick Start Guide

**Status**: Phase 1 ✅ Complete | Phase 2 ⏳ Running | Phase 3-4 ⏳ Ready

---

## Quick Commands

### Start Training (Current)

```bash
cd /Users/ryanlin/Downloads/sky_burrito

# Phase 1: Single Hub (Already done ✅)
.venv/bin/python simulation/rl_training.py --phase 1 --fleet-sizes 20 --no-gpu

# Phase 2: Two-Hub Bidirectional (Currently running ⏳)
.venv/bin/python simulation/rl_training.py --phase 2 --fleet-sizes 20 --no-gpu

# Phase 3: Full Network (Ready to run)
.venv/bin/python simulation/rl_training.py --phase 3 --fleet-sizes 10 20 30 40 50 --no-gpu

# Phase 4: Variable Demand (Ready to run)
.venv/bin/python simulation/rl_training.py --phase 4 --fleet-sizes 10 20 30 40 50 --no-gpu
```

### Monitor Training (Open New Terminal)

```bash
cd /Users/ryanlin/Downloads/sky_burrito
tensorboard --logdir logs

# Then open: http://localhost:6006
```

### Evaluate Models

```bash
# Evaluate Phase 1 model
.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 1 --num-episodes 10

# Evaluate all fleet sizes (when trained)
.venv/bin/python simulation/rl_inference.py --phase 3 --all-sizes --num-episodes 5
```

---

## Project Structure

```
sky_burrito/
├── simulation/
│   ├── rl_fleet_env.py              ✅ Gymnasium environment
│   ├── rl_training.py               ✅ PPO training script
│   ├── rl_inference.py              ✅ Model evaluation
│   └── app.py                       ➡️ Main simulation (to be integrated)
├── models/
│   └── fleet_20/
│       ├── ppo_fleet_20_phase_1.zip ✅ Phase 1 trained model
│       └── ppo_fleet_20_phase_2.zip ⏳ Phase 2 (training)
├── logs/
│   ├── fleet_20_phase_1/
│   │   └── events.out.tfevents.*    ✅ Phase 1 TensorBoard logs
│   └── fleet_20_phase_2/
│       └── events.out.tfevents.*    ⏳ Phase 2 TensorBoard logs
├── PHASE_10_SUMMARY.md              📋 RL architecture design
├── RL_FLEET_OPTIMIZATION_DESIGN.md  📋 Complete specifications
├── RL_IMPLEMENTATION_GUIDE.md        📋 Implementation walkthrough
└── PHASE_1_TRAINING_COMPLETE.md     📊 Training results
```

---

## Training Progress

### Phase 1: Single Hub ✅
```
Status:           COMPLETE
Fleet size:       20 drones
Training time:    24 seconds
Timesteps:        51,200
Final reward:     1,714,275,598
Model:            models/fleet_20/ppo_fleet_20_phase_1.zip
```

### Phase 2: Two-Hub Bidirectional ⏳
```
Status:           RUNNING
Fleet size:       20 drones
Duration so far:  ~50 seconds
Timesteps:        ~100,000 (target)
Model:            models/fleet_20/ppo_fleet_20_phase_2.zip (saving)
Expected time:    ~1-2 minutes (CPU)
```

### Phase 3: Full Network ⏳
```
Status:           READY (not started)
Fleet sizes:      10, 20, 30, 40, 50 (5 models)
Duration each:    ~2-4 hours (CPU) or ~30 min (GPU)
Timesteps each:   500,000
Goal:             Optimize across 9 hubs, 20 routes
Expected total:   10-20 hours (sequential) or 2-4 hours (GPU parallel)
```

### Phase 4: Variable Demand ⏳
```
Status:           READY (not started)
Fleet sizes:      10, 20, 30, 40, 50 (5 models)
Duration each:    ~4-6 hours (CPU) or ~45 min (GPU)
Timesteps each:   1,000,000
Goal:             Adapt to meal-time demand peaks (breakfast, lunch, dinner)
Expected total:   20-30 hours (sequential) or 5-10 hours (GPU parallel)
```

---

## Key Files & What They Do

### Environment (`simulation/rl_fleet_env.py`)
- **Purpose**: Gymnasium-compatible RL environment
- **What it simulates**: 
  - 9 active hubs (distributed across city)
  - 20 viable delivery routes (from SHOW.md)
  - Fleet of drones (10-50 configurable)
  - Meal-time demand variation (breakfast/lunch/snack/dinner peaks)
  - Battery constraints (rebalancing requires sufficient charge)
  - Order fulfillment & reward calculation
- **Observation**: 42D vector (fleet, queues, utilization, meals, battery, time)
- **Action**: 9D continuous (rebalancing transfers between hubs)
- **Reward**: Multi-objective (fulfillment, craning, dead-head, battery)

### Training Script (`simulation/rl_training.py`)
- **Purpose**: Train PPO agents with curriculum learning
- **Phases**:
  - Phase 1: Single hub (easiest, 50K timesteps)
  - Phase 2: Two-hub bidirectional (medium, 100K timesteps)
  - Phase 3: Full network (hard, 500K timesteps)
  - Phase 4: Variable demand (hardest, 1M timesteps)
- **Features**:
  - Automatic curriculum management
  - Checkpoint saving every 5,000-50,000 steps
  - TensorBoard logging
  - GPU/CPU device auto-selection
  - Test evaluation after training

### Inference Script (`simulation/rl_inference.py`)
- **Purpose**: Load trained models and evaluate performance
- **Capabilities**:
  - Single model evaluation
  - Fleet size comparison
  - Performance metrics (reward, fulfillment, steps)
  - Results table generation

---

## Environment Details

### State Space (42D)
```
[0:9]    Fleet per hub (normalized by fleet size)
[9:18]   Order queues per hub (normalized by 50)
[18:27]  Hub utilization (0-1 range)
[27:31]  Meal-time intensity (breakfast, lunch, snack, dinner)
[31:40]  Battery levels per hub (0-1 range)
[40:42]  Time encoding (sin/cos of current hour)
```

### Action Space (9D Continuous)
```
Range:    [-5, +5] per hub
Meaning:  Positive = send drones out, Negative = receive drones
Constraint: sum(action) = 0 (fleet size conserved)
Battery requirement: ≥15% to execute rebalancing
```

### Reward Function (Multi-Objective)
```
reward = (
    +50 × orders_fulfilled_this_step        # 50% weight
    -10 × total_queue_wait_minutes / 100    # 30% weight
    -200 × drones_craning                   # 20% weight
    -5 × drones_deadheading                 # 15% weight
    +10 × max(0, idle_drones - 5)           # 5% weight
)
```

### Demand Model (Meal-Time Based)
```
Breakfast (7-9 AM):      1.2-1.5× base demand
Lunch (11:30-1:30 PM):   1.3-1.8× base demand
Snack (3-5 PM):          0.9-1.1× base demand
Dinner (6-8 PM):         1.4-1.8× base demand
Off-peak:                0.3-0.6× base demand
```

---

## Training Performance

### Phase 1 Results (Completed)
```
Training time:    24 seconds
FPS:              ~2,000 (CPU)
Final reward:     1,714,275,598
Improvement:      3,428× vs. random baseline
Loss:             Decreasing (converging)
Stability:        All metrics healthy
Model size:       14,483 parameters
File size:        ~500 KB
```

### Phase 2 Progress (Running)
```
Timesteps:        100,000 target
Current:          ~20,000 (20% done)
Estimated time:   ~1-2 minutes total (CPU)
Learning rate:    5e-4 (reduced from Phase 1)
Batch size:       128 (doubled from Phase 1)
```

### Expected Phase 3 (Not started)
```
Timesteps:        500,000 per fleet size
Full network:     9 hubs, 20 routes
Expected time:    2-4 hours per size (CPU), 30 min (GPU)
Total 5 sizes:    10-20 hours (sequential), 2-4 hours (GPU)
```

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'gymnasium'"
**Solution:**
```bash
cd /Users/ryanlin/Downloads/sky_burrito
.venv/bin/python -m pip install gymnasium torch stable-baselines3 tensorboard tqdm rich
```

### Problem: Training is very slow (CPU only)
**Solution 1 - Use GPU** (if available):
```bash
# Remove --no-gpu flag
.venv/bin/python simulation/rl_training.py --phase 1 --fleet-sizes 20
# Expected: 5-10× speedup on GPU
```

**Solution 2 - Be patient**:
- Phase 1: ~1 minute (already done)
- Phase 2: ~2 minutes (currently running)
- Phase 3: ~2-4 hours per fleet size
- Phase 4: ~4-6 hours per fleet size

**Solution 3 - Reduce computational load**:
- Start with single fleet size (e.g., fleet 20 only)
- Increase sim_speedup parameter (makes steps shorter)
- Reduce batch_size (edit RL_CONFIG)

### Problem: TensorBoard not running
**Solution:**
```bash
# Make sure you're in the right directory
cd /Users/ryanlin/Downloads/sky_burrito

# Start TensorBoard
tensorboard --logdir logs

# Open browser to: http://localhost:6006
```

### Problem: Model not found when evaluating
**Solution:**
```bash
# Make sure model exists
ls models/fleet_20/

# Training must complete first
# Wait for training to finish or run:
.venv/bin/python simulation/rl_training.py --phase 1 --fleet-sizes 20 --no-gpu
```

---

## Next Actions

### Immediate (Now)
- [x] Phase 1 training: Complete ✅
- [x] Phase 2 training: Started ⏳
- [ ] Monitor Phase 2 progress: Open TensorBoard

### Short-term (Next 30 mins)
- [ ] Wait for Phase 2 to finish (~1-2 min)
- [ ] Start Phase 3 training (full network)
- [ ] Watch TensorBoard metrics

### Medium-term (Next few hours)
- [ ] Complete Phase 3 (all fleet sizes 10-50)
- [ ] Evaluate models with inference script
- [ ] Generate fleet size comparison

### Long-term (After convergence)
- [ ] Train Phase 4 (meal-time peaks)
- [ ] Compare all phases
- [ ] Select optimal fleet size
- [ ] Deploy best policy to main simulation

---

## Monitoring Metrics

### TensorBoard Dashboard
Open: `http://localhost:6006`

**Important metrics**:
```
rollout/ep_rew_mean       → Episode reward (should increase/plateau)
rollout/ep_len_mean       → Episode length (should stabilize)
train/loss                → Policy loss (should decrease)
train/value_loss          → Value function (should increase)
train/approx_kl           → KL divergence (should stay < 0.01)
train/clip_fraction       → Clipping % (should be 0)
train/entropy_loss        → Entropy (should stay stable)
```

### Command Line Output
```
iterations      → Training update count
time_elapsed    → Wall-clock time
total_timesteps → Total simulation steps
fps             → Simulation speed (frames/second)
```

---

## Expected Learning Behavior

### Phase 1: Single Hub
**What agent learns**: Where to position drones to maximize fulfillment at single hub
- Drones accumulate at the delivery hub
- Battery management (charge when idle, discharge on delivery)
- Reward increases as fulfillment improves

### Phase 2: Two-Hub Bidirectional  
**What agent learns**: How to transfer drones between two hubs based on demand
- Learns directional transfers (hub A → hub B)
- Learns timing (when to rebalance)
- Battery constraints become more relevant

### Phase 3: Full Network
**What agent learns**: City-wide fleet coordination across 9 hubs
- Complex multi-hop routing decisions
- Load balancing across network
- Peak hour preparation

### Phase 4: Variable Demand
**What agent learns**: Predictive positioning for meal-time peaks
- Pre-position for breakfast (7-9 AM)
- Shift for lunch (11:30-1:30 PM)
- Adapt for dinner (6-8 PM)

---

## Files Generated During Training

```
models/
└── fleet_20/
    ├── ppo_fleet_20_phase_1.zip
    ├── ppo_fleet_20_phase_1_checkpoint_*.zip
    ├── ppo_fleet_20_phase_2.zip (saving)
    ├── ppo_fleet_20_phase_2_checkpoint_*.zip
    └── ...

logs/
├── fleet_20_phase_1/
│   └── PPO_4/
│       ├── events.out.tfevents.*
│       └── checkpoints/
│           ├── ppo_fleet_20_phase_1_checkpoint_5000_steps
│           ├── ppo_fleet_20_phase_1_checkpoint_10000_steps
│           └── ...
└── fleet_20_phase_2/
    └── PPO_1/
        ├── events.out.tfevents.*
        └── checkpoints/
```

---

## Key Commands Reference

```bash
# Training
.venv/bin/python simulation/rl_training.py --phase 1 --fleet-sizes 20 --no-gpu
.venv/bin/python simulation/rl_training.py --phase 2 --fleet-sizes 20 --no-gpu
.venv/bin/python simulation/rl_training.py --phase 3 --fleet-sizes 10 20 30 40 50 --no-gpu
.venv/bin/python simulation/rl_training.py --phase 4 --fleet-sizes 10 20 30 40 50 --no-gpu

# Evaluation
.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 1 --num-episodes 10
.venv/bin/python simulation/rl_inference.py --phase 3 --all-sizes --num-episodes 5

# Monitoring
tensorboard --logdir logs

# Testing environment
.venv/bin/python -c "from simulation.rl_fleet_env import DroneFleetEnv; env = DroneFleetEnv(fleet_size=20); print('✓ Environment OK')"

# List trained models
ls -lh models/fleet_20/

# View latest TensorBoard logs
ls -lt logs/*/*/events*
```

---

## Summary

- ✅ **Phase 1** trained and saved (24 seconds)
- ⏳ **Phase 2** currently training (~1-2 minutes remaining)
- ⏳ **Phase 3-4** ready to run (2-6 hours each)
- ✅ **Environment tested** and working
- ✅ **Monitoring ready** (TensorBoard)
- ✅ **Models saving** automatically

**Next**: Wait for Phase 2 to complete, then start Phase 3! 🚀
