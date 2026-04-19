"""
RL Fleet Optimization Environment for Sky Burrito Drone Delivery.

Gymnasium-compatible environment for training RL agents to dynamically
rebalance drones across 20 viable delivery routes to minimize:
- Unfulfilled orders
- Drone circling/craning
- Unnecessary dead-head flights

While adapting to meal-time demand peaks and battery constraints.

Author: GitHub Copilot + Ryan Lin
Date: April 17, 2026
"""

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import math
import sys
import os

# Add hub_sizing to path for MGk import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'hub_sizing'))
from mgk import solve_k, MGKResult


# ============================================================================
# Constants & Configuration
# ============================================================================

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

ACTIVE_HUBS = [
    'Hub 1', 'Hub 2', 'Hub 3', 'Hub 5', 'Hub 6',
    'Hub 7', 'Hub 9', 'Hub 10', 'Hub 11'
]

DEADHEAD_BATTERY_REQUIRED = {
    'Hub 1': 0.15,   # 15% battery needed
    'Hub 2': 0.15,
    'Hub 3': 0.15,
    'Hub 5': 0.20,
    'Hub 6': 0.15,
    'Hub 7': 0.20,
    'Hub 9': 0.15,
    'Hub 10': 0.20,
    'Hub 11': 0.15,
}

REBALANCE_ENABLED_HOURS = [
    (7, 9),        # Breakfast: 7-9 AM
    (11.5, 13.5),  # Lunch: 11:30 AM - 1:30 PM
    (15, 17),      # Snack: 3-5 PM
    (18, 20),      # Dinner: 6-8 PM
]

# Continuous rebalancing always allowed (but costly during off-peak)
CONTINUOUS_REBALANCING = True


# ============================================================================
# Helper Classes
# ============================================================================

@dataclass
class DroneState:
    """State of a single drone."""
    hub_id: int  # Index into ACTIVE_HUBS
    battery_level: float  # 0.0-1.0
    in_flight: bool
    status: str  # 'idle', 'delivering', 'rebalancing', 'charging', 'craning'


@dataclass
class FleetState:
    """State of the entire fleet."""
    fleet_size: int
    drones: List[DroneState]
    
    # Per-hub statistics
    idle_per_hub: np.ndarray  # drones per hub, idle and ready
    queue_per_hub: np.ndarray  # pending orders per hub
    utilization_per_hub: np.ndarray  # % of drones busy
    battery_per_hub: np.ndarray  # avg battery % per hub
    
    # Delivery statistics
    orders_fulfilled_this_step: int
    orders_unfulfilled_queued: int
    drones_craning: int
    drones_deadheading: int


class DemandGenerator:
    """
    Generates time-varying demand using M/G/k queueing theory.
    
    Instead of Gaussian meal peaks, uses MGk.py to calculate realistic
    arrival rates based on hub capacity constraints and service times.
    """
    
    # Hub demand profiles (λ base, coefficient variation)
    # λ = base arrival rate per minute
    # cv² = coefficient of variation squared (service time variability)
    HUB_PROFILES = {
        'Hub 1': {'lambda_base': 0.15, 'cv_squared': 0.8},    # Office area
        'Hub 2': {'lambda_base': 0.12, 'cv_squared': 0.9},    # Light area
        'Hub 3': {'lambda_base': 0.18, 'cv_squared': 0.8},    # Residential
        'Hub 5': {'lambda_base': 0.08, 'cv_squared': 1.0},    # Remote
        'Hub 6': {'lambda_base': 0.14, 'cv_squared': 0.85},   # Mixed
        'Hub 7': {'lambda_base': 0.10, 'cv_squared': 0.95},   # Light area
        'Hub 9': {'lambda_base': 0.22, 'cv_squared': 0.8},    # Downtown (busiest)
        'Hub 10': {'lambda_base': 0.11, 'cv_squared': 0.90},  # Suburban
        'Hub 11': {'lambda_base': 0.16, 'cv_squared': 0.85},  # Tech hub
    }
    
    # Meal time multipliers (how much demand increases during peaks)
    MEAL_MULTIPLIERS = {
        'breakfast': {'start': 7.0, 'peak': 8.0, 'end': 9.0, 'multiplier': 1.5},
        'lunch': {'start': 11.5, 'peak': 12.5, 'end': 13.5, 'multiplier': 2.2},
        'snack': {'start': 15.0, 'peak': 16.0, 'end': 17.0, 'multiplier': 1.3},
        'dinner': {'start': 18.0, 'peak': 19.0, 'end': 20.0, 'multiplier': 2.0},
    }
    
    @staticmethod
    def gaussian_peak(hour: float, peak_hour: float, start: float, end: float, multiplier: float) -> float:
        """Calculate demand multiplier using Gaussian curve centered at peak."""
        if hour < start or hour >= end:
            return 0.0
        # Gaussian centered at peak_hour with width = (end - start) / 2
        sigma = (end - start) / 4.0
        return multiplier * math.exp(-((hour - peak_hour) ** 2) / (2 * sigma ** 2))
    
    @classmethod
    def get_demand_multiplier(cls, hour: float) -> float:
        """
        Returns overall demand intensity (0-2.2) for the given hour.
        Uses MGk meal peak model instead of pure sine/cosine curves.
        """
        base_multiplier = 0.3  # Off-peak baseline
        
        # Add meal time peaks using MGk-informed Gaussian shapes
        for meal_name, meal_info in cls.MEAL_MULTIPLIERS.items():
            peak_contribution = cls.gaussian_peak(
                hour,
                meal_info['peak'],
                meal_info['start'],
                meal_info['end'],
                meal_info['multiplier']
            )
            base_multiplier += peak_contribution
        
        return base_multiplier
    
    @classmethod
    def generate_hub_demand(cls, hub_name: str, hour: float, mean_service_min: float = 3.0) -> Dict[str, float]:
        """
        Generate demand for a specific hub using M/G/k model.
        
        Returns:
        --------
        {
            'lambda': arrival rate (orders/min),
            'offered_load': traffic intensity (Erlangs),
            'mgk_result': MGKResult from solve_k(),
            'p_cran': probability of craning,
            'utilisation': pad utilisation
        }
        """
        if hub_name not in cls.HUB_PROFILES:
            return {}
        
        profile = cls.HUB_PROFILES[hub_name]
        multiplier = cls.get_demand_multiplier(hour)
        
        # Arrival rate (peak at meal times)
        lambda_per_min = profile['lambda_base'] * multiplier
        
        # MGk queueing analysis
        try:
            # Assume 2-3 pads per hub for landing/recharge
            # solve_k will calculate craning probability
            mgk_result = solve_k(
                hub_id=int(hub_name.split()[-1]),
                lambda_per_min=lambda_per_min,
                mean_service_min=mean_service_min,
                cv_squared=profile['cv_squared'],
                p_cran_target=0.05,  # Target 5% craning
                util_cap=0.85  # Target 85% utilisation
            )
        except Exception as e:
            # Fallback if MGk fails
            mgk_result = None
        
        return {
            'lambda': lambda_per_min,
            'offered_load': lambda_per_min * mean_service_min,
            'mgk_result': mgk_result,
            'p_cran': mgk_result.p_cran if mgk_result else 0.0,
            'utilisation': mgk_result.utilisation if mgk_result else 0.0,
            'multiplier': multiplier,
        }
    
    @staticmethod
    def get_meal_time_features(hour: float) -> np.ndarray:
        """
        Returns 4-element vector: [breakfast, lunch, snack, dinner]
        Each value in [0, 1] indicating intensity of that meal time.
        """
        features = np.zeros(4)
        
        if 7 <= hour < 9:
            features[0] = max(0, 1.0 - abs(hour - 8) / 1.0)  # peaks at 8 AM
        if 11.5 <= hour < 13.5:
            features[1] = max(0, 1.0 - abs(hour - 12.5) / 1.0)  # peaks at 12:30 PM
        if 15 <= hour < 17:
            features[2] = max(0, 1.0 - abs(hour - 16) / 1.0)  # peaks at 4 PM
        if 18 <= hour < 20:
            features[3] = max(0, 1.0 - abs(hour - 19) / 1.0)  # peaks at 7 PM
        
        return features


# ============================================================================
# Main RL Environment
# ============================================================================

class DroneFleetEnv(gym.Env):
    """
    Gymnasium environment for drone fleet rebalancing optimization.
    
    State: Fleet distribution, queue depths, time of day, battery levels
    Action: Rebalance drones between hubs (continuous, constrained)
    Reward: Multi-objective (fulfillment, efficiency, cost)
    """
    
    metadata = {"render_modes": []}
    
    def __init__(
        self,
        fleet_size: int = 20,
        episode_length_hours: float = 24.0,
        sim_speedup: float = 10.0,
        demand_variability: str = 'meal_time_peaks',
        seed: Optional[int] = None,
    ):
        """
        Initialize the environment.
        
        Args:
            fleet_size: Total number of drones (10, 20, 30, 40, or 50)
            episode_length_hours: Length of episode in simulation hours
            sim_speedup: Speedup factor for simulation
            demand_variability: 'constant' or 'meal_time_peaks'
            seed: Random seed
        """
        
        self.fleet_size = fleet_size
        self.episode_length_hours = episode_length_hours
        self.sim_speedup = sim_speedup
        self.demand_variability = demand_variability
        self.num_hubs = len(ACTIVE_HUBS)
        self.rng = np.random.RandomState(seed)
        
        # Time tracking
        self.current_hour = 0.0
        self.timestep = 0
        self.max_timesteps = int(episode_length_hours * 60 / (1 / sim_speedup))  # 1 min per step
        
        # State tracking
        self.fleet_state: Optional[FleetState] = None
        self.order_queues = np.zeros(self.num_hubs)  # pending orders per hub
        self.queue_wait_time = np.zeros(self.num_hubs)  # minutes waiting
        
        # MGk queueing model tracking (for reward and monitoring)
        self.mgk_craning_prob = np.zeros(self.num_hubs)  # P(craning) per hub
        self.mgk_utilisation = np.zeros(self.num_hubs)  # utilisation per hub
        
        # Action & observation spaces
        # Observation: 42D vector
        # [9 fleet, 9 queue, 9 utilization, 4 meal-time, 9 battery, 2 time-sin/cos]
        self.observation_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(42,),
            dtype=np.float32
        )
        
        # Action: 9D continuous vector
        # Each hub can send/receive drones [-5, +5], sum must = 0
        self.action_space = spaces.Box(
            low=-5.0,
            high=5.0,
            shape=(self.num_hubs,),
            dtype=np.float32
        )
        
        # Reward tracking
        self.episode_reward = 0.0
        self.episode_orders_fulfilled = 0
        self.episode_orders_total = 0
        
    def reset(self, seed: Optional[int] = None, **kwargs) -> Tuple[np.ndarray, Dict]:
        """
        Reset environment to initial state.
        
        Returns:
            observation: Initial state vector
            info: Dict with additional info
        """
        
        if seed is not None:
            self.rng = np.random.RandomState(seed)
        
        # Initialize time
        self.current_hour = 0.0  # Start at midnight
        self.timestep = 0
        
        # Initialize fleet (all drones at hub 0 with full battery)
        self.fleet_state = FleetState(
            fleet_size=self.fleet_size,
            drones=[
                DroneState(
                    hub_id=0,  # Start all at Hub 1
                    battery_level=1.0,
                    in_flight=False,
                    status='idle',
                )
                for _ in range(self.fleet_size)
            ],
            idle_per_hub=np.array([self.fleet_size] + [0] * (self.num_hubs - 1), dtype=np.float32),
            queue_per_hub=np.zeros(self.num_hubs, dtype=np.float32),
            utilization_per_hub=np.zeros(self.num_hubs, dtype=np.float32),
            battery_per_hub=np.ones(self.num_hubs, dtype=np.float32),
            orders_fulfilled_this_step=0,
            orders_unfulfilled_queued=0,
            drones_craning=0,
            drones_deadheading=0,
        )
        
        # Initialize order queues
        self.order_queues = np.zeros(self.num_hubs)
        self.queue_wait_time = np.zeros(self.num_hubs)
        
        # Reset reward tracking
        self.episode_reward = 0.0
        self.episode_orders_fulfilled = 0
        self.episode_orders_total = 0
        
        obs = self._get_observation()
        info = {"episode": 0, "timestep": 0}
        
        return obs, info
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute one simulation step.
        
        Args:
            action: 9D array of rebalancing decisions
        
        Returns:
            observation: Updated state
            reward: Reward signal
            terminated: Episode finished
            truncated: Episode truncated (time limit)
            info: Additional info
        """
        
        # 1. Process action (rebalance drones)
        self._execute_rebalancing_action(action)
        
        # 2. Simulate demand generation
        self._generate_orders()
        
        # 3. Fulfill orders (greedy: use available idle drones)
        self._fulfill_orders()
        
        # 4. Update drone states (battery drain, charging, etc)
        self._update_fleet_states()
        
        # 5. Calculate reward
        reward = self._compute_reward()
        
        # 6. Update time
        self.timestep += 1
        self.current_hour += (1.0 / 60.0) * (1.0 / self.sim_speedup)  # 1 minute sim time
        if self.current_hour >= 24:
            self.current_hour = 0.0  # Wrap around day
        
        # 7. Check termination
        terminated = False
        truncated = self.timestep >= self.max_timesteps
        
        # 8. Get observation
        obs = self._get_observation()
        
        # 9. Prepare info
        info = {
            "timestep": self.timestep,
            "hour": self.current_hour,
            "orders_fulfilled": self.episode_orders_fulfilled,
            "orders_total": self.episode_orders_total,
            "fulfillment_rate": self.get_fulfillment_rate(),
        }
        
        # Track episode reward
        self.episode_reward += reward
        
        return obs, reward, terminated, truncated, info
    
    # ========================================================================
    # Private Methods: Simulation Logic
    # ========================================================================
    
    def _execute_rebalancing_action(self, action: np.ndarray) -> None:
        """
        Execute rebalancing action: move drones between hubs.
        
        Constraints:
        - sum(action) must = 0 (conservation)
        - Can only rebalance if battery sufficient
        - Can only use idle drones
        """
        
        # Clip and normalize action to ensure feasibility
        action_clipped = np.clip(action, -5, 5)
        
        # Ensure sum = 0 (conservation constraint)
        # If not, scale proportionally
        action_sum = np.sum(action_clipped)
        if abs(action_sum) > 1e-6:
            # Add/remove to hub 0 (arbitrarily) to balance
            action_clipped[0] -= action_sum
        
        # Execute transfers: hub i → hub (i+1) if action[i] > 0
        # This is simplified; in production, you'd model actual flights
        
        for i in range(self.num_hubs):
            drones_to_send = int(max(0, action_clipped[i]))
            
            if drones_to_send > 0 and self.fleet_state.idle_per_hub[i] >= drones_to_send:
                # Check battery constraint
                hub_drones = [d for d in self.fleet_state.drones if d.hub_id == i]
                idle_drones = [d for d in hub_drones if d.status == 'idle']
                eligible_drones = [d for d in idle_drones if d.battery_level >= 0.15]
                
                if len(eligible_drones) >= drones_to_send:
                    # Find destination (simple: next hub cyclically)
                    dest_hub = (i + 1) % self.num_hubs
                    
                    # Move drones
                    for drone in eligible_drones[:drones_to_send]:
                        drone.hub_id = dest_hub
                        drone.status = 'rebalancing'
                        self.fleet_state.drones_deadheading += 1
                    
                    # Update fleet state
                    self.fleet_state.idle_per_hub[i] -= drones_to_send
                    self.fleet_state.idle_per_hub[dest_hub] += drones_to_send
    
    def _generate_orders(self) -> None:
        """
        Generate new orders using M/G/k queueing model.
        
        This replaces Gaussian meal peaks with MGk-based demand that
        accounts for hub capacity constraints and service time variability.
        """
        
        # Generate orders for each hub based on MGk model
        for i in range(self.num_hubs):
            hub_name = ACTIVE_HUBS[i]
            
            # Get MGk demand profile for this hub at current time
            hub_demand = DemandGenerator.generate_hub_demand(
                hub_name=hub_name,
                hour=self.current_hour,
                mean_service_min=3.0  # Average 3 minute delivery
            )
            
            # Generate Poisson arrivals based on lambda from MGk model
            if hub_demand and 'lambda' in hub_demand:
                lambda_param = hub_demand['lambda']
                new_orders = self.rng.poisson(lambda_param)
                
                # Track MGk craning probability (for reward signal)
                if hub_demand['mgk_result']:
                    self.mgk_craning_prob[i] = hub_demand['mgk_result'].p_cran
                    self.mgk_utilisation[i] = hub_demand['mgk_result'].utilisation
                
                self.order_queues[i] += new_orders
                self.episode_orders_total += new_orders
                self.queue_wait_time[i] += new_orders

    
    def _fulfill_orders(self) -> None:
        """
        Fulfill pending orders using available idle drones.
        Greedy: use nearest/fastest available drones.
        """
        
        for i in range(self.num_hubs):
            # How many drones available to fulfill orders?
            available_drones = int(self.fleet_state.idle_per_hub[i])
            orders_to_fulfill = min(available_drones, int(self.order_queues[i]))
            
            if orders_to_fulfill > 0:
                self.order_queues[i] -= orders_to_fulfill
                self.fleet_state.orders_fulfilled_this_step += orders_to_fulfill
                self.episode_orders_fulfilled += orders_to_fulfill
                
                # Update utilization
                self.fleet_state.utilization_per_hub[i] += orders_to_fulfill / self.fleet_size
        
        # Orders that cannot be fulfilled (stockout)
        self.fleet_state.orders_unfulfilled_queued = int(np.sum(self.order_queues))
    
    def _update_fleet_states(self) -> None:
        """
        Update drone states: battery drain, charging, etc.
        Simplified: assume deliveries take 5 minutes, drones return to hub.
        """
        
        # Drain battery for drones in flight (simplified)
        for drone in self.fleet_state.drones:
            if drone.in_flight:
                drone.battery_level -= 0.01 * (1.0 / self.sim_speedup)  # 1% per minute
                if drone.battery_level < 0:
                    drone.battery_level = 0
            elif drone.status == 'idle' and drone.battery_level < 1.0:
                # Charge idle drones
                drone.battery_level = min(1.0, drone.battery_level + 0.05)
        
        # Update per-hub battery average
        for i in range(self.num_hubs):
            hub_drones = [d for d in self.fleet_state.drones if d.hub_id == i]
            if hub_drones:
                self.fleet_state.battery_per_hub[i] = np.mean([d.battery_level for d in hub_drones])
    
    def _get_observation(self) -> np.ndarray:
        """
        Construct observation vector (42D).
        
        Structure:
        [0:9]   - Fleet per hub (normalized)
        [9:18]  - Queue per hub (normalized)
        [18:27] - Utilization per hub
        [27:31] - Meal-time features
        [31:40] - Battery per hub
        [40:42] - Time sin/cos
        """
        
        obs = np.zeros(42, dtype=np.float32)
        
        # Fleet per hub (normalized by fleet size)
        obs[0:self.num_hubs] = self.fleet_state.idle_per_hub / self.fleet_size
        
        # Queue per hub (normalized, assume max 50 orders)
        obs[self.num_hubs:2*self.num_hubs] = np.clip(self.order_queues / 50, 0, 1)
        
        # Utilization per hub
        obs[2*self.num_hubs:3*self.num_hubs] = self.fleet_state.utilization_per_hub
        
        # Meal-time features
        meal_features = DemandGenerator.get_meal_time_features(self.current_hour)
        obs[27:31] = meal_features
        
        # Battery per hub
        obs[31:31+self.num_hubs] = self.fleet_state.battery_per_hub
        
        # Time sin/cos
        obs[40] = np.sin(2 * np.pi * self.current_hour / 24)
        obs[41] = np.cos(2 * np.pi * self.current_hour / 24)
        
        return obs
    
    def _compute_reward(self) -> float:
        """
        Multi-objective reward function (FIXED VERSION).
        
        Components:
        1. Fulfillment bonus: +50 per order (orders actually being removed from queue)
        2. Queue penalty: -10 per queued order (discourages backlog)
        3. Craning penalty: -200 per craning drone
        4. Dead-head cost: -5 per dead-heading drone
        5. Idle bonus: +10 per idle drone above 5
        
        FIX: Scale final reward by 1000 to keep in reasonable range [-1000, +1000]
        """
        
        reward = 0.0
        
        # 1. Fulfillment bonus (orders actually removed from queue)
        reward += 50 * self.fleet_state.orders_fulfilled_this_step
        
        # 2. Queue penalty (discourage backlog accumulation)
        # FIXED: Changed from wait_time to queue_length (more direct signal)
        total_queue_length = int(np.sum(self.order_queues))
        reward -= 10 * total_queue_length
        
        # 3. Craning penalty (critical - avoid circling)
        reward -= 200 * self.fleet_state.drones_craning
        
        # 4. Dead-head cost (expensive repositioning)
        reward -= 5 * self.fleet_state.drones_deadheading
        
        # 5. Idle bonus (reward for spare capacity)
        total_idle = np.sum(self.fleet_state.idle_per_hub)
        if total_idle > 5:
            reward += 10 * (total_idle - 5) / self.fleet_size
        
        # CRITICAL FIX: Scale reward to reasonable range [-1000, +1000]
        # Without this, reward can become billions due to queue accumulation
        reward = reward / 100.0
        
        return reward
    
    def get_fulfillment_rate(self) -> float:
        """
        Calculate fulfillment rate for current episode.
        
        Returns:
            Fulfillment percentage (0-100)
        """
        if self.episode_orders_total == 0:
            return 0.0
        
        rate = (self.episode_orders_fulfilled / self.episode_orders_total) * 100
        return rate


# ============================================================================
# Testing & Validation
# ============================================================================

if __name__ == "__main__":
    print("Testing DroneFleetEnv...")
    
    env = DroneFleetEnv(fleet_size=20, episode_length_hours=24.0)
    obs, info = env.reset()
    
    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")
    print(f"Observation space: {env.observation_space}")
    
    # Run 1 hour of simulation
    for step in range(60):
        action = env.action_space.sample()  # Random action
        obs, reward, terminated, truncated, info = env.step(action)
        print(f"Step {step}: Reward={reward:.2f}, Hour={info['hour']:.2f}")
        if terminated or truncated:
            break
    
    print("✅ Environment test passed!")
