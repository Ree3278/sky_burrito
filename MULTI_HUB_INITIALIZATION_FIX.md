# Multi-Hub Drone Fleet Initialization Fix

## Problem Statement
The `DroneFleetEnv.reset()` method was initializing **all drones at hub 0** regardless of the number of active hubs or fleet size. This was inefficient for multi-hub environments where demand varies significantly across hubs.

## Root Cause
In the original code, all drones were hardcoded to start at hub 0:
```python
self.fleet_state = FleetState(
    fleet_size=self.fleet_size,
    drones=[
        DroneState(
            hub_id=0,  # ← ALL DRONES AT HUB 0
            battery_level=1.0,
            in_flight=False,
            status='idle',
        )
        for _ in range(self.fleet_size)
    ],
    idle_per_hub=np.array([self.fleet_size] + [0] * (self.num_hubs - 1), ...),
    ...
)
```

This meant:
- **20-drone fleet**: All 20 at hub 0
- **30-drone fleet**: All 30 at hub 0
- **9-hub environment**: 8 hubs empty, 1 hub overloaded

## Solution
Added intelligent drone distribution across hubs based on demand profiles:

### 1. New Method: `_distribute_drones_across_hubs()`
Located in `simulation/rl_fleet_env.py` after the `reset()` method.

```python
def _distribute_drones_across_hubs(self) -> np.ndarray:
    """
    Distribute drones across hubs based on demand profiles.
    
    For multi-hub environments, allocates drones proportionally to each hub's
    demand profile (base lambda from DemandGenerator.HUB_PROFILES).
    
    Returns:
        Array of drone counts per hub, sums to fleet_size
    """
    if self.num_hubs <= 1:
        # Single hub: all drones at hub 0
        return np.array([self.fleet_size] + [0] * (self.num_hubs - 1), dtype=np.float32)
    
    # Multi-hub: distribute proportionally to demand
    hub_names = ACTIVE_HUBS
    demand_weights = np.array([
        DemandGenerator.HUB_PROFILES[hub]['lambda_base']
        for hub in hub_names
    ])
    
    # Normalize weights to probabilities
    demand_probs = demand_weights / demand_weights.sum()
    
    # Allocate drones proportionally
    drone_allocation = (demand_probs * self.fleet_size).astype(int)
    
    # Adjust for rounding errors: add remaining drones to hub with highest demand
    remaining = self.fleet_size - drone_allocation.sum()
    if remaining > 0:
        highest_demand_hub = np.argmax(demand_weights)
        drone_allocation[highest_demand_hub] += remaining
    
    return drone_allocation.astype(np.float32)
```

### 2. Modified `reset()` Method
Updated the reset method to use the distribution function:

```python
# Initialize fleet - distribute drones across hubs proportionally to demand
idle_per_hub_list = self._distribute_drones_across_hubs()

# Create drone list with distributed hub assignments
drones_list = []
drone_id = 0
for hub_id, count in enumerate(idle_per_hub_list):
    for _ in range(int(count)):
        drones_list.append(
            DroneState(
                hub_id=hub_id,
                battery_level=1.0,
                in_flight=False,
                status='idle',
            )
        )
        drone_id += 1

self.fleet_state = FleetState(
    fleet_size=self.fleet_size,
    drones=drones_list,
    idle_per_hub=np.array(idle_per_hub_list, dtype=np.float32),
    ...
)
```

## Results

### Before Fix
Fleet of 20 drones across 9 hubs:
```
Drones per hub: [20, 0, 0, 0, 0, 0, 0, 0, 0]
```
- Hub 9 (λ=2.2, busiest): 0 drones ❌

### After Fix
Fleet of 20 drones across 9 hubs:
```
Drones per hub: [2, 1, 2, 1, 2, 1, 8, 1, 2]
Hub 9 gets 8 drones (40% of fleet) ✓
```

Demand-weighted allocation:
| Hub | λ (Demand) | Allocation | % |
|-----|-----------|------------|-----|
| Hub 1 | 1.5 | 2 | 10% |
| Hub 2 | 1.2 | 1 | 5% |
| Hub 3 | 1.8 | 2 | 10% |
| Hub 5 | 0.8 | 1 | 5% |
| Hub 6 | 1.4 | 2 | 10% |
| Hub 7 | 1.0 | 1 | 5% |
| **Hub 9** | **2.2** | **8** | **40%** |
| Hub 10 | 1.1 | 1 | 5% |
| Hub 11 | 1.6 | 2 | 10% |

### Verification Tests Passed
✅ Multi-hub drone distribution verified
✅ Drone-hub consistency verified (DroneState hub_id matches idle_per_hub counts)
✅ Battery initialization verified (all drones start at 1.0)
✅ Multi-hub step execution successful
✅ RL training compatibility verified

## Benefits
1. **Faster convergence**: Drones start near high-demand hubs
2. **Reduced inefficiency**: Fewer dead-head flights needed
3. **Better coverage**: All hubs have some drones initially
4. **Demand-aware**: High-demand hubs get more drones (Hub 9: 40% of fleet)
5. **Scalable**: Works for any fleet size and hub count

## Testing
Run tests to verify the fix:
```bash
# Test multi-hub initialization and consistency
python test_multi_hub_env.py

# Test RL training step execution
python test_rl_multi_hub_steps.py
```

## Files Modified
- `simulation/rl_fleet_env.py`: Updated `reset()` method and added `_distribute_drones_across_hubs()` helper method
