# RL Fleet Optimization for Sky Burrito Drone Delivery

**Document Date:** April 17, 2026  
**Purpose:** Design document for RL-based dynamic fleet rebalancing  
**Status:** Design Phase Complete - Ready for Implementation

---

## 📋 Executive Summary

**Objective:** Train an RL agent to dynamically rebalance drones across 20 viable routes to:
- Minimize unfulfilled orders (stockouts)
- Minimize drone circling/craning
- Minimize dead-head (rebalancing) flights
- Adapt to meal-time demand peaks (breakfast, lunch, dinner, snacks)

**Key Constraints:**
- Only 20 viable routes (defined in SHOW.md)
- Fleet size: Explore 10, 20, 30, 40, 50 drones (test each)
- Dynamic rebalancing during peak hours (7-9am, 11:30am-1:30pm, 6-8pm, 3-5pm)
- Continuous rebalancing decision-making
- Battery constraints: Only rebalance if drone has enough charge
- Hub activation: Some hubs close if underutilized (RL learns which)

**Technology:**
- Framework: Gymnasium (gym.Env)
- Algorithm: PPO (Proximal Policy Optimization)
- Hardware: GPU training (CUDA/MPS)
- Implementation: PyTorch + Stable-Baselines3

---

## 🗺️ Viable Routes (Fixed Set)

**All 20 routes from SHOW.md (cannot be changed, only rebalanced):**

```python
VIABLE_ROUTES = [
    ('Hub 11', 'Hub 9', 2.40),   # Route 1: Score 1035.5
    ('Hub 9', 'Hub 11', 2.40),   # Route 2: Score 1008.0
    ('Hub 10', 'Hub 6', 2.44),   # Route 3: Score 1004.4
    ('Hub 1', 'Hub 9', 2.25),    # Route 4: Score 952.0
    ('Hub 9', 'Hub 1', 2.25),    # Route 5: Score 948.2
    ('Hub 11', 'Hub 2', 2.18),   # Route 6: Score 947.1
    ('Hub 6', 'Hub 10', 2.44),   # Route 7: Score 944.5
    ('Hub 2', 'Hub 11', 2.18),   # Route 8: Score 942.8
    ('Hub 2', 'Hub 1', 2.14),    # Route 9: Score 934.8
    ('Hub 9', 'Hub 6', 2.29),    # Route 10: Score 928.5
    ('Hub 3', 'Hub 6', 2.18),    # Route 11: Score 924.2
    ('Hub 1', 'Hub 2', 2.14),    # Route 12: Score 918.5
    ('Hub 6', 'Hub 9', 2.29),    # Route 13: Score 901.1
    ('Hub 10', 'Hub 11', 2.14),  # Route 14: Score 885.6
    ('Hub 11', 'Hub 10', 2.14),  # Route 15: Score 883.4
    ('Hub 6', 'Hub 3', 2.18),    # Route 16: Score 873.3
    ('Hub 7', 'Hub 1', 1.87),    # Route 17: Score 802.3
    ('Hub 5', 'Hub 6', 1.89),    # Route 18: Score 800.9
    ('Hub 1', 'Hub 7', 1.87),    # Route 19: Score 787.4
    ('Hub 2', 'Hub 6', 1.91),    # Route 20: Score 783.3
]

ACTIVE_HUBS = set(['Hub 1', 'Hub 2', 'Hub 3', 'Hub 5', 'Hub 6', 'Hub 7', 'Hub 9', 'Hub 10', 'Hub 11'])
# Hubs 4, 8, 12 inactive (no viable routes)
```

---

## 🧠 RL Environment Design

### State Space (Observation)

```python
class State:
    """
    32-dimensional continuous state vector
    """
    
    # 1. Fleet Distribution (9 values: drones per active hub)
    #    Range: [0, fleet_size]
    fleet_per_hub = [
        idle_drones_hub_1,
        idle_drones_hub_2,
        idle_drones_hub_3,
        idle_drones_hub_5,
        idle_drones_hub_6,
        idle_drones_hub_7,
        idle_drones_hub_9,
        idle_drones_hub_10,
        idle_drones_hub_11,
    ]
    
    # 2. Order Queue Depth (9 values: pending orders per hub)
    #    Range: [0, 50] (normalized)
    queue_per_hub = [
        orders_waiting_hub_1,
        orders_waiting_hub_2,
        ...
        orders_waiting_hub_11,
    ]
    
    # 3. Hub Utilization (9 values: % of drones busy)
    #    Range: [0, 1] (percentage)
    utilization_per_hub = [
        util_hub_1,
        util_hub_2,
        ...
    ]
    
    # 4. Time Context (4 values: meal-time encoding)
    #    Soft one-hot: [breakfast_active, lunch_active, dinner_active, snack_active]
    #    Range: [0, 1] (continuous, peaks at peak times)
    meal_time_features = [
        breakfast_intensity,  # peaks 7-9am
        lunch_intensity,      # peaks 11:30am-1:30pm
        snack_intensity,      # peaks 3-5pm
        dinner_intensity,     # peaks 6-8pm
    ]
    
    # 5. Battery State (9 values: avg battery % per hub)
    #    Range: [0, 1]
    battery_per_hub = [
        avg_battery_hub_1,
        ...
    ]
    
    # 6. Global Status (2 values)
    time_of_day_sin = sin(2π × hour / 24)
    time_of_day_cos = cos(2π × hour / 24)
    
    # TOTAL: 9 + 9 + 9 + 4 + 9 + 2 = 42 dimensions
```

### Action Space (Continuous)

```python
class Action:
    """
    Continuous rebalancing action.
    Each hub can send/receive drones, subject to constraints.
    
    Action = [Δ_h1, Δ_h2, ..., Δ_h9]
    
    Where:
    - Δ_hi ∈ [-5, +5]: net drones to move OUT of hub i
    - Negative: hub receives drones
    - sum(Δ) must = 0 (conservation: total fleet fixed)
    - Can only rebalance if:
      * Drones at hub i have >15% battery
      * Hub i has idle drones to spare
      * Battery sufficient for dead-head flight
    
    Example:
    Action = [+2, 0, 0, -1, +1, 0, 0, -2, 0]
    Meaning:
    - Hub 1 sends 2 drones
    - Hub 5 receives 1 drone
    - Hub 6 sends 1 drone
    - Hub 10 receives 2 drones
    - Others: no change
    """
    
    n_actions = 9  # one per hub
    action_space = Box(low=-5, high=+5, shape=(9,), dtype=np.float32)
```

---

## 🎯 Reward Function

```python
def compute_reward(prev_state, action, curr_state, sim_time_hours):
    """
    Multi-component reward signal, weighted for importance.
    """
    
    reward = 0.0
    
    # ========================
    # 1. FULFILLMENT BONUS (Heaviest weight: 50%)
    # ========================
    # Penalty for unfulfilled orders (orders stuck in queue)
    for hub_id in range(9):
        queue_length = curr_state.queue_per_hub[hub_id]
        queue_wait_time_minutes = curr_state.queue_wait_time[hub_id]
        
        # Penalty increases if orders wait too long
        if queue_wait_time_minutes > 5:  # 5 minute SLA
            penalty = -100 * (queue_wait_time_minutes / 5)  # heavy penalty
        else:
            penalty = 0
        
        reward += penalty
    
    # Bonus for orders fulfilled this step
    orders_fulfilled_this_step = (
        prev_state.total_queue_length - curr_state.total_queue_length
    )
    reward += 50 * orders_fulfilled_this_step  # +50 per order
    
    
    # ========================
    # 2. CRANING PENALTY (Critical: 30%)
    # ========================
    # Circling drones = wasted energy + customer frustration
    craning_drones = curr_state.drones_circling
    reward -= 200 * craning_drones  # -200 per craning drone
    
    
    # ========================
    # 3. DEAD-HEAD COST (Moderate: 15%)
    # ========================
    # Rebalancing flights cost money but are necessary
    deadhead_drones = curr_state.drones_in_deadhead
    deadhead_cost = deadhead_drones * 5  # $5 per operational drone
    reward -= deadhead_cost
    
    
    # ========================
    # 4. IDLE READINESS BONUS (Mild: 5%)
    # ========================
    # Encourage strategic stockpiling during off-peak
    total_idle = sum(curr_state.fleet_per_hub)
    if total_idle > 5:
        reward += 10 * (total_idle - 5)  # reward excess capacity off-peak
    
    
    # ========================
    # 5. MEAL-TIME ADAPTATION BONUS (Mild: 0%)
    # ========================
    # Reward: does fleet distribution match demand pattern?
    for hub_id in range(9):
        expected_demand = curr_state.meal_time_features * demand_profile[hub_id]
        actual_fleet = curr_state.fleet_per_hub[hub_id]
        
        # Small bonus if fleet slightly above expected demand
        if actual_fleet > expected_demand * 0.8:
            reward += 5
    
    
    # ========================
    # 6. HUB ACTIVATION EFFICIENCY (Rare: sparse)
    # ========================
    # Penalty if hub is open but has no demand/fleet
    for hub_id in ACTIVE_HUBS:
        if (curr_state.queue_per_hub[hub_id] == 0 and 
            curr_state.fleet_per_hub[hub_id] == 0):
            reward -= 10  # discourage empty hub operation
    
    
    # ========================
    # 7. EPISODE BONUS (End-of-episode only)
    # ========================
    if sim_time_hours >= EPISODE_LENGTH:
        net_fulfillment = total_orders_fulfilled / total_orders_demanded
        if net_fulfillment > 0.95:
            reward += 500  # strong bonus for >95% fulfillment
        elif net_fulfillment > 0.90:
            reward += 200  # moderate bonus for >90%
    
    return reward
```

### Reward Weighting Summary

```
Fulfillment:      ████████████████████ 50%
Craning Penalty:  ██████████████       30%
Dead-Head Cost:   █████████            15%
Idle Bonus:       ███                  5%
Efficiency:        0%
Episode Bonus:    Sparse (end-of-episode)

Total: Weighted multi-objective, normalized
```

---

## ⏰ Demand Profile (Time-Varying)

```python
class DemandSchedule:
    """
    Demand varies by time of day, peaking during meal times.
    """
    
    def get_demand_multiplier(hour: float) -> float:
        """
        Returns demand intensity (0-1.5) based on time of day.
        """
        
        # Breakfast: 7-9 AM
        if 7 <= hour < 9:
            return 1.2 + 0.3 * sin(π * (hour - 7) / 2)  # peaks at 8 AM
        
        # Mid-morning dip: 9-11:30 AM
        elif 9 <= hour < 11.5:
            return 0.6
        
        # Lunch: 11:30 AM - 1:30 PM
        elif 11.5 <= hour < 13.5:
            return 1.3 + 0.5 * sin(π * (hour - 11.5) / 2)  # peaks at 12:30 PM
        
        # Afternoon: 1:30-3 PM
        elif 13.5 <= hour < 15:
            return 0.7
        
        # Snack: 3-5 PM
        elif 15 <= hour < 17:
            return 0.9 + 0.2 * sin(π * (hour - 15) / 2)  # peaks at 4 PM
        
        # Evening: 5-6 PM
        elif 17 <= hour < 18:
            return 0.8
        
        # Dinner: 6-8 PM
        elif 18 <= hour < 20:
            return 1.4 + 0.4 * sin(π * (hour - 18) / 2)  # peaks at 7 PM
        
        # Night: 8 PM - 7 AM
        else:
            return 0.3  # minimal overnight demand
    
    @staticmethod
    def get_meal_time_features(hour: float) -> np.array:
        """
        Returns 4-element vector for meal-time encoding.
        [breakfast, lunch, snack, dinner]
        """
        features = np.zeros(4)
        
        if 7 <= hour < 9:
            features[0] = 1.0 if hour == 8 else (hour - 7) / 2
        if 11.5 <= hour < 13.5:
            features[1] = 1.0 if hour == 12.5 else (hour - 11.5) / 2
        if 15 <= hour < 17:
            features[2] = 1.0 if hour == 16 else (hour - 15) / 2
        if 18 <= hour < 20:
            features[3] = 1.0 if hour == 19 else (hour - 18) / 2
        
        return features
```

---

## 🔋 Battery Constraints

```python
class BatteryConstraint:
    """
    Drones cannot rebalance if battery insufficient.
    """
    
    DEADHEAD_BATTERY_REQUIRED = {
        # Battery % needed for dead-head flight to each destination
        # Based on: 2-2.5 km average distance, 10 Wh per km
        'Hub 1': 0.15,   # 15% battery
        'Hub 2': 0.15,
        'Hub 3': 0.15,
        'Hub 5': 0.20,
        'Hub 6': 0.15,
        'Hub 7': 0.20,
        'Hub 9': 0.15,
        'Hub 10': 0.20,
        'Hub 11': 0.15,
    }
    
    def can_rebalance(
        source_hub: str,
        destination_hub: str,
        fleet_battery_levels: List[float],  # % per drone
    ) -> int:
        """
        Returns: number of drones that CAN rebalance (have sufficient battery)
        """
        battery_needed = DEADHEAD_BATTERY_REQUIRED[destination_hub]
        eligible_count = sum(
            1 for bat in fleet_battery_levels 
            if bat >= battery_needed + 0.05  # 5% safety margin
        )
        return eligible_count
```

---

## 🎮 Training Curriculum

```python
class TrainingCurriculum:
    """
    Progressive training: start simple, increase complexity.
    """
    
    # Phase 1: Single hub (Hub 6 = downtown sink)
    PHASE_1 = {
        'duration': 100,  # 100 episodes
        'active_hubs': ['Hub 6'],  # Only one hub
        'fleet_sizes': [10],
        'routes': ['Hub 1→6', 'Hub 2→6', 'Hub 3→6', 'Hub 9→6', 'Hub 10→6'],
        'demand_multiplier': 1.0,
        'goal': 'Learn to stockpile at sink',
    }
    
    # Phase 2: Two-hub bidirectional (Hub 11 ↔ Hub 9)
    PHASE_2 = {
        'duration': 200,
        'active_hubs': ['Hub 11', 'Hub 9'],
        'fleet_sizes': [15, 20],
        'routes': ['Hub 11→9', 'Hub 9→11'],
        'demand_multiplier': 1.0,
        'goal': 'Learn cross-hub rebalancing',
    }
    
    # Phase 3: Core network (9 hubs, 20 routes)
    PHASE_3 = {
        'duration': 500,
        'active_hubs': list(ACTIVE_HUBS),
        'fleet_sizes': [10, 15, 20, 25, 30, 35, 40, 45, 50],
        'routes': VIABLE_ROUTES,  # All 20 routes
        'demand_multiplier': 1.0,
        'goal': 'Full network optimization',
    }
    
    # Phase 4: Variable demand (with meal-time peaks)
    PHASE_4 = {
        'duration': 1000,
        'active_hubs': list(ACTIVE_HUBS),
        'fleet_sizes': [10, 20, 30, 40, 50],
        'routes': VIABLE_ROUTES,
        'demand_multiplier': 1.2,  # 20% higher average
        'demand_variability': 'meal_time_peaks',
        'goal': 'Adapt to demand patterns',
    }
```

---

## 🚀 Implementation Files Structure

```
simulation/
├── rl_fleet_env.py            (NEW) Gym environment
├── rl_fleet_agent.py          (NEW) PPO agent
├── rl_training.py             (NEW) Main training loop
├── rl_inference.py            (NEW) Deployment script
├── fleet_manager.py           (NEW) Fleet state tracking
└── rebalancing_policy.py      (NEW) Action execution

models/
├── ppo_fleet_policy_fleet10.pt  (Trained: 10 drones)
├── ppo_fleet_policy_fleet20.pt  (Trained: 20 drones)
├── ppo_fleet_policy_fleet30.pt  (Trained: 30 drones)
├── ppo_fleet_policy_fleet40.pt  (Trained: 40 drones)
└── ppo_fleet_policy_fleet50.pt  (Trained: 50 drones)

logs/
├── training_logs/
│   ├── fleet10_training.log
│   ├── fleet20_training.log
│   └── ...
└── tensorboard/
    └── ppo_fleet_optimization/
```

---

## 🔧 Configuration

```python
# RL_CONFIG.yaml
RL:
  algorithm: PPO
  learning_rate: 3e-4
  batch_size: 128
  n_steps: 1800  # 30 min sim-time between updates
  n_epochs: 5
  gamma: 0.99
  gae_lambda: 0.95
  clip_range: 0.2
  ent_coef: 0.01
  
TRAINING:
  total_timesteps: 1_000_000
  save_interval: 10_000
  eval_interval: 50_000
  
SIMULATION:
  sim_speedup: 10x  # 1 real second = 10 sim seconds
  episode_length: 24  # 24 hours per episode
  
FLEET:
  sizes: [10, 20, 30, 40, 50]
  battery_capacity: 100  # % charge
  rebalance_frequency: continuous  # continuous during peak hours
  
REBALANCING:
  enabled_hours:
    breakfast: [7, 9]      # 7-9 AM
    lunch: [11.5, 13.5]    # 11:30 AM - 1:30 PM
    snack: [15, 17]        # 3-5 PM
    dinner: [18, 20]       # 6-8 PM
  always_enabled: true      # Continuous rebalancing
  
DEMAND:
  peak_orders_per_hub_per_hour: 30
  off_peak_orders_per_hub_per_hour: 5
  variability: meal_time_peaks
```

---

## 📊 Success Metrics

```python
class SuccessMetrics:
    """
    Evaluate RL agent performance.
    """
    
    # Primary metrics
    fulfillment_rate: float  # % orders fulfilled (target: >95%)
    craning_frequency: float  # events/hour (target: <5)
    deadhead_percentage: float  # % of fleet doing rebalancing (target: <15%)
    
    # Secondary metrics
    avg_queue_time: float  # minutes (target: <3)
    idle_drone_count: float  # ready drones (target: >3)
    battery_efficiency: float  # % battery used (target: 70-90%)
    
    # Efficiency
    cost_per_delivery: float  # $ (target: <$0.50 total)
    orders_per_drone: float  # orders/drone/day (target: >20)
    
    # Optimization
    fleet_utilization: float  # % (target: 60-80%)
    rebalancing_cost: float  # $ (target: <$0.05/delivery)
```

---

## 🎯 Deployment Strategy

### Pre-Deployment (Phase 0)
- Train on GPU with curriculum learning
- Evaluate on unseen demand patterns
- Create inference deployment script

### Live Testing (Phase 1)
- Load best policy (fleet_30 with meal-time peaks)
- Run in simulation with real demand data
- Monitor metrics in real-time
- A/B test: RL-optimized vs. baseline (fixed fleet allocation)

### Production (Phase 2)
- Deploy RL agent to fleet manager
- Continuous rebalancing during peak hours
- Monitor for model drift
- Periodic retraining with new data

---

## 📝 Key Implementation Notes

1. **Constraints-Aware Actions:**
   - Action clipping: ensure sum(Δ) = 0
   - Battery checking: only rebalance if sufficient charge
   - Queue awareness: don't drain hubs with pending orders

2. **Meal-Time Peaks:**
   - Features injected into state vector
   - Demand multiplier varies by hour
   - Agent learns to pre-position fleet

3. **Continuous Rebalancing:**
   - Not discrete time steps
   - Action taken every 1 minute sim-time during peak hours
   - Off-peak: rebalancing allowed but discouraged (high dead-head cost)

4. **Hub Closure (Emergent):**
   - No explicit hub closing in RL
   - Economic pressure: empty hubs get negative reward
   - Agent learns to concentrate fleet where demand is

5. **GPU Training:**
   - Use `device = torch.device("cuda" if torch.cuda.is_available() else "cpu")`
   - Batch size: 128-256
   - Expected: 2-3 hours per fleet size on V100 GPU

---

## 🚀 Next Steps

1. Create `simulation/rl_fleet_env.py` (Gymnasium environment)
2. Create `simulation/fleet_manager.py` (state tracking)
3. Create `simulation/rl_fleet_agent.py` (PPO implementation)
4. Create `simulation/rl_training.py` (training loop)
5. Test on Phase 1 (single hub)
6. Iterate through Phases 2-4
7. Document results and insights

---

**Document Version:** 1.0  
**Status:** ✅ Design Complete - Ready for Implementation  
**Author:** GitHub Copilot + Ryan Lin  
**Last Updated:** April 17, 2026
