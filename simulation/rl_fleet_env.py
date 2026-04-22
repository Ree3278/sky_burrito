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

# Add project root to path for cross-package imports
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'hub_sizing'))
sys.path.insert(0, _PROJECT_ROOT)

from hub_sizing.demand import hub_profiles_from_setup_hubs
from hub_sizing.mgk import solve_k, MGKResult
from rebalancing.ghost_logic import GhostHeuristic, GhostConfig, GhostMove
from simulation.environment import SimulationSetup, load_or_build_simulation_setup
from settings.rl import (
    ACTION_MAX,
    ACTION_MIN,
    CONTINUOUS_REBALANCING,
    CRANING_PENALTY,
    DEADHEAD_BATTERY_REQUIRED,
    DEADHEAD_PENALTY,
    DEFAULT_DEMAND_VARIABILITY,
    DELIVERY_DURATION_MINUTES,
    DEMAND_BASELINE_MULTIPLIER,
    FULFILLMENT_BONUS,
    GHOST_HEARTBEAT_MINUTES,
    IDLE_BONUS_SCALE,
    IDLE_BONUS_THRESHOLD,
    MEAL_MULTIPLIERS as RL_MEAL_MULTIPLIERS,
    MGK_MEAN_SERVICE_MIN,
    MGK_P_CRAN_TARGET,
    MGK_UTIL_CAP,
    QUEUE_OBSERVATION_CAP,
    QUEUE_PENALTY_CAP_MULTIPLIER,
    QUEUE_PENALTY_PER_ORDER,
    REBALANCE_ENABLED_HOURS,
    REWARD_NORMALIZATION,
    STARVED_HUB_PENALTY,
    STARVED_HUB_QUEUE_THRESHOLD,
    TIME_ENCODING_PERIOD_HOURS,
)


# ============================================================================
# Constants & Configuration
# ============================================================================


# ============================================================================
# Helper Classes
# ============================================================================

@dataclass
class DroneState:
    """State of a single drone."""
    hub_id: int  # Index into the environment's hub_names list
    battery_level: float  # 0.0-1.0
    in_flight: bool
    status: str  # 'idle', 'delivering', 'rebalancing', 'charging', 'craning'
    busy_steps_remaining: int = 0


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
    # INCREASED 10x to fix demand generation issue
    HUB_PROFILES: Dict[str, Dict[str, float]] = {}
    
    # Meal time multipliers (how much demand increases during peaks)
    MEAL_MULTIPLIERS = RL_MEAL_MULTIPLIERS
    
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
        base_multiplier = DEMAND_BASELINE_MULTIPLIER
        
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
    def generate_hub_demand(cls, hub_name: str, hour: float, mean_service_min: float = MGK_MEAN_SERVICE_MIN) -> Dict[str, float]:
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
                p_cran_target=MGK_P_CRAN_TARGET,
                util_cap=MGK_UTIL_CAP,
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
        demand_variability: str = DEFAULT_DEMAND_VARIABILITY,
        active_hubs: Optional[List[str]] = None,
        simulation_setup: Optional[SimulationSetup] = None,
        seed: Optional[int] = None,
    ):
        """
        Initialize the environment.
        
        Args:
            fleet_size: Total number of drones (10, 20, 30, 40, or 50)
            episode_length_hours: Length of episode in simulation hours
            sim_speedup: Simulation granularity expressed as
                `steps_per_hour / 60`. A value of 60 means 1 minute per step.
            demand_variability: 'constant' or 'meal_time_peaks'
            active_hubs: Optional subset of hubs active for this phase
            seed: Random seed
        """
        if sim_speedup <= 0:
            raise ValueError("sim_speedup must be positive")

        self.setup = simulation_setup or load_or_build_simulation_setup()
        self.fleet_size = fleet_size
        self.episode_length_hours = episode_length_hours
        self.sim_speedup = sim_speedup
        self.demand_variability = demand_variability
        self.hub_names = list(self.setup.active_hub_names)
        self.num_hubs = len(self.hub_names)
        self.active_hubs = list(active_hubs) if active_hubs is not None else list(self.hub_names)
        invalid_hubs = sorted(set(self.active_hubs) - set(self.hub_names))
        if invalid_hubs:
            raise ValueError(f"Unknown active hubs: {invalid_hubs}")
        self.active_hub_indices = [self.hub_names.index(hub) for hub in self.active_hubs]
        self.viable_routes = [
            (f"Hub {route.origin_id}", f"Hub {route.destination_id}", route.straight_line_m / 1000.0)
            for route in self.setup.routes
            if f"Hub {route.origin_id}" in self.active_hubs
            and f"Hub {route.destination_id}" in self.active_hubs
        ]
        self.hub_profiles = hub_profiles_from_setup_hubs(
            self.setup.hubs,
            service_cv_squared=self.setup.service_cv_squared,
        )
        DemandGenerator.HUB_PROFILES = self.hub_profiles
        self.rng = np.random.RandomState(seed)
        
        # Time tracking
        self.current_hour = 0.0
        self.timestep = 0
        self.step_minutes = 60.0 / sim_speedup
        self.max_timesteps = max(1, int(round((episode_length_hours * 60) / self.step_minutes)))
        self.delivery_duration_steps = max(1, math.ceil(DELIVERY_DURATION_MINUTES / self.step_minutes))
        
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
            low=ACTION_MIN,
            high=ACTION_MAX,
            shape=(self.num_hubs,),
            dtype=np.float32
        )
        
        # Reward tracking
        self.episode_reward = 0.0
        self.episode_orders_fulfilled = 0
        self.episode_orders_total = 0
        self.last_reward_components: Dict[str, float] = {}

        # ── Ghost Heuristic (pressure-based dead-head rebalancing) ──────────
        # Fires every `_ghost_heartbeat_steps` environment steps alongside the
        # RL agent's action.  Heartbeat is time-based: targets ~5 sim-minutes
        # regardless of sim_speedup.
        self._ghost_config = GhostConfig()
        self._ghost_heuristic = GhostHeuristic(
            hub_names=self.hub_names,
            viable_routes=self.viable_routes,
            config=self._ghost_config,
        )
        # heartbeat: every 5 simulated minutes
        self._ghost_heartbeat_steps: int = max(1, round(GHOST_HEARTBEAT_MINUTES / self.step_minutes))
        self._ghost_step_counter: int = 0
        # Episode-level ghost stats (reset on env.reset())
        self.episode_ghost_moves: int = 0
        self.episode_ghost_drones: int = 0
        
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
        
        # Initialize fleet - distribute drones across hubs proportionally to demand
        # For multi-hub environments, distribute based on hub demand profiles
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
        self.mgk_craning_prob = np.zeros(self.num_hubs)
        self.mgk_utilisation = np.zeros(self.num_hubs)
        
        # Reset reward tracking
        self.episode_reward = 0.0
        self.episode_orders_fulfilled = 0
        self.episode_orders_total = 0
        self.last_reward_components = {}

        # Reset ghost heuristic counters
        self._ghost_step_counter = 0
        self.episode_ghost_moves = 0
        self.episode_ghost_drones = 0

        self._sync_fleet_state()
        
        obs = self._get_observation()
        info = {
            "episode": 0,
            "timestep": 0,
            "active_hubs": self.active_hubs,
            "step_minutes": self.step_minutes,
        }
        
        return obs, info
    
    def _distribute_drones_across_hubs(self) -> np.ndarray:
        """
        Distribute drones across hubs based on demand profiles.
        
        For multi-hub environments, allocates drones proportionally to each hub's
        demand profile (base lambda from the loaded simulation setup).
        
        Returns:
            Array of drone counts per hub, sums to fleet_size
        """
        drone_allocation = np.zeros(self.num_hubs, dtype=int)

        if not self.active_hub_indices:
            return drone_allocation.astype(np.float32)

        if len(self.active_hub_indices) == 1:
            drone_allocation[self.active_hub_indices[0]] = self.fleet_size
            return drone_allocation.astype(np.float32)

        demand_weights = np.array([
            self.hub_profiles[self.hub_names[idx]]['lambda_base']
            for idx in self.active_hub_indices
        ])
        demand_probs = demand_weights / demand_weights.sum()
        active_allocation = (demand_probs * self.fleet_size).astype(int)
        drone_allocation[self.active_hub_indices] = active_allocation

        remaining = self.fleet_size - drone_allocation.sum()
        if remaining > 0:
            highest_demand_local_idx = int(np.argmax(demand_weights))
            highest_demand_hub = self.active_hub_indices[highest_demand_local_idx]
            drone_allocation[highest_demand_hub] += remaining
        
        return drone_allocation.astype(np.float32)


    def _reset_step_counters(self) -> None:
        """Reset per-step metrics so rewards are not cumulative artifacts."""
        self.fleet_state.orders_fulfilled_this_step = 0
        self.fleet_state.drones_craning = 0
        self.fleet_state.drones_deadheading = 0

    def _sync_fleet_state(self) -> None:
        """Synchronize aggregate hub metrics from individual drone states."""
        idle_per_hub = np.zeros(self.num_hubs, dtype=np.float32)
        busy_per_hub = np.zeros(self.num_hubs, dtype=np.float32)
        drones_per_hub = np.zeros(self.num_hubs, dtype=np.float32)
        battery_sum_per_hub = np.zeros(self.num_hubs, dtype=np.float32)

        for drone in self.fleet_state.drones:
            hub_id = drone.hub_id
            drones_per_hub[hub_id] += 1
            battery_sum_per_hub[hub_id] += drone.battery_level
            if drone.status == 'idle':
                idle_per_hub[hub_id] += 1
            else:
                busy_per_hub[hub_id] += 1

        utilization = np.zeros(self.num_hubs, dtype=np.float32)
        battery_per_hub = np.zeros(self.num_hubs, dtype=np.float32)
        active_mask = drones_per_hub > 0
        utilization[active_mask] = busy_per_hub[active_mask] / drones_per_hub[active_mask]
        battery_per_hub[active_mask] = battery_sum_per_hub[active_mask] / drones_per_hub[active_mask]

        self.fleet_state.idle_per_hub = idle_per_hub
        self.fleet_state.queue_per_hub = self.order_queues.astype(np.float32)
        self.fleet_state.utilization_per_hub = utilization
        self.fleet_state.battery_per_hub = battery_per_hub
        self.fleet_state.orders_unfulfilled_queued = int(np.sum(self.order_queues))

    def _idle_drones_at_hub(self, hub_id: int, min_battery: float = 0.0) -> List[DroneState]:
        """Return idle drones at a hub that satisfy a minimum battery threshold."""
        return [
            drone
            for drone in self.fleet_state.drones
            if drone.hub_id == hub_id
            and drone.status == 'idle'
            and drone.battery_level >= min_battery
        ]

    def _get_next_active_hub(self, hub_id: int) -> int:
        """Choose the next active hub cyclically for simplified rebalancing."""
        if hub_id not in self.active_hub_indices or len(self.active_hub_indices) <= 1:
            return hub_id

        current_position = self.active_hub_indices.index(hub_id)
        next_position = (current_position + 1) % len(self.active_hub_indices)
        return self.active_hub_indices[next_position]
    
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
        
        self._reset_step_counters()

        # 1. Update drone states from the previous step
        self._update_fleet_states()

        # 2. Process RL agent's action (cyclic rebalancing)
        self._execute_rebalancing_action(action)

        # 3. Ghost heuristic heartbeat (pressure-based dead-head rebalancing).
        #    Fires every ~5 simulated minutes alongside the RL policy.
        #    Handles slow tidal drift that the cyclic RL action cannot fix.
        self._ghost_step_counter += 1
        if self._ghost_step_counter >= self._ghost_heartbeat_steps:
            self._ghost_step_counter = 0
            self._execute_ghost_heuristic()

        # 4. Simulate demand generation
        self._generate_orders()

        # 5. Fulfill orders using hub-local idle drones
        self._fulfill_orders()

        self._sync_fleet_state()
        
        # 5. Calculate reward
        reward = self._compute_reward()
        
        # 6. Update time
        self.timestep += 1
        self.current_hour += self.step_minutes / 60.0
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
            "active_hubs": self.active_hubs,
            "step_minutes": self.step_minutes,
            "reward_components": dict(self.last_reward_components),
            # Ghost heuristic diagnostics
            "ghost_moves_episode": self.episode_ghost_moves,
            "ghost_drones_episode": self.episode_ghost_drones,
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

        Routing — demand-aware (replaces original cyclic hub[i+1]):
          For each hub i where action[i] > 0, drones are sent to the active
          hub j (j ≠ i) with the highest demand pressure score:

              pressure[j] = order_queues[j] / (idle_per_hub[j] + 1)

          This allows the agent to learn direct hub-to-hub redistribution,
          rather than depending on multi-hop cyclic chains to solve tidal drift.

        Constraints:
        - sum(action) must = 0 (conservation)
        - Can only rebalance if battery sufficient
        - Can only use idle drones
        """
        action_clipped = np.clip(action, ACTION_MIN, ACTION_MAX)
        action_sum = np.sum(action_clipped)
        if abs(action_sum) > 1e-6:
            action_clipped[0] -= action_sum

        # Pre-compute demand pressure for routing decisions.
        pressure = np.where(
            self.fleet_state.idle_per_hub + 1 > 0,
            self.order_queues / (self.fleet_state.idle_per_hub + 1.0),
            0.0,
        )

        for i in self.active_hub_indices:
            drones_to_send = int(max(0, action_clipped[i]))
            if drones_to_send <= 0:
                continue

            min_battery = DEADHEAD_BATTERY_REQUIRED[self.hub_names[i]]
            eligible_drones = self._idle_drones_at_hub(i, min_battery=min_battery)
            if len(eligible_drones) < drones_to_send:
                continue

            # Route to the active hub with highest demand pressure (not self).
            dest_pressure = pressure.copy()
            dest_pressure[i] = -1.0
            # Restrict to active hub indices only.
            mask = np.full(self.num_hubs, -np.inf)
            mask[self.active_hub_indices] = dest_pressure[self.active_hub_indices]
            dest_hub = int(np.argmax(mask))
            if dest_hub == i or mask[dest_hub] <= 0.0:
                dest_hub = self._get_next_active_hub(i)  # fallback to cyclic
            if dest_hub == i:
                continue

            for drone in eligible_drones[:drones_to_send]:
                drone.hub_id = dest_hub
                drone.battery_level = max(0.0, drone.battery_level - min_battery)
                self.fleet_state.drones_deadheading += 1
    
    def _execute_ghost_heuristic(self) -> int:
        """
        Phase 3 — Environment hook for the Ghost Heuristic.

        Runs between the RL action and demand generation so that repositioned
        drones are available to serve the orders that arrive this step.

        Execution flow
        --------------
        1. Suppression check    — skip entirely during dinner rush (18–20 h).
        2. Pressure computation — P_i = idle_i − queue_i − T_i per hub.
        3. Donor–recipient match— greedy nearest-flight-time pairing.
        4. Guardrail checks     — battery floor + craning-risk check per move.
        5. Teleport execution   — same instant-teleport as RL rebalancing action.

        Returns
        -------
        int
            Number of drones actually relocated this tick.
        """
        # ── Guardrail: dinner-rush suppression ──────────────────────────────
        if self._ghost_heuristic.should_suppress(self.current_hour):
            self._ghost_heuristic.suppressed_ticks += 1
            return 0

        # ── Phase 1: compute pressure ────────────────────────────────────────
        target_inv = self._ghost_heuristic.compute_target_inventory(self.fleet_size)
        pressures  = self._ghost_heuristic.compute_pressure(
            idle_per_hub     = self.fleet_state.idle_per_hub,
            order_queues     = self.order_queues,
            target_inventory = target_inv,
        )

        # ── Phase 2: match donors to recipients ─────────────────────────────
        moves: List[GhostMove] = self._ghost_heuristic.match_donors_to_recipients(
            pressures          = pressures,
            active_hub_indices = self.active_hub_indices,
        )

        if not moves:
            return 0

        # ── Phase 3 / 4: execute moves with guardrails ──────────────────────
        drones_relocated = 0

        for move in moves:
            # Guardrail: craning check — skip if recipient is already congested.
            if not GhostHeuristic.recipient_is_safe(
                recipient_idx        = move.recipient_idx,
                utilization_per_hub  = self.fleet_state.utilization_per_hub,
            ):
                continue

            # Guardrail: battery floor — only eligible drones may dead-head.
            battery_cost = DEADHEAD_BATTERY_REQUIRED.get(
                self.hub_names[move.donor_idx], 0.15
            )
            min_soc = max(self._ghost_config.battery_floor, battery_cost)
            eligible = self._idle_drones_at_hub(move.donor_idx, min_battery=min_soc)

            actual_n = min(move.n_drones, len(eligible))
            if actual_n <= 0:
                continue

            # Execute: teleport drones from donor → recipient hub, drain battery.
            for drone in eligible[:actual_n]:
                drone.hub_id       = move.recipient_idx
                drone.battery_level = max(0.0, drone.battery_level - battery_cost)
                self.fleet_state.drones_deadheading += 1

            drones_relocated        += actual_n
            self.episode_ghost_moves += 1
            self.episode_ghost_drones += actual_n
            self._ghost_heuristic.total_ghost_moves  += 1
            self._ghost_heuristic.total_ghost_drones += actual_n

        return drones_relocated

    def _generate_orders(self) -> None:
        """
        Generate new orders using M/G/k queueing model.
        
        This replaces Gaussian meal peaks with MGk-based demand that
        accounts for hub capacity constraints and service time variability.
        """
        
        # Generate orders for each hub based on MGk model
        for i in range(self.num_hubs):
            hub_name = self.hub_names[i]
            if hub_name not in self.active_hubs:
                self.mgk_craning_prob[i] = 0.0
                self.mgk_utilisation[i] = 0.0
                continue
            
            # Get MGk demand profile for this hub at current time
            hub_demand = DemandGenerator.generate_hub_demand(
                hub_name=hub_name,
                hour=self.current_hour,
                mean_service_min=MGK_MEAN_SERVICE_MIN
            )
            
            # Generate Poisson arrivals based on lambda from MGk model
            if hub_demand and 'lambda' in hub_demand:
                lambda_param = hub_demand['lambda'] * self.step_minutes
                new_orders = self.rng.poisson(lambda_param)
                
                # Track MGk craning probability (for reward signal)
                if hub_demand['mgk_result']:
                    self.mgk_craning_prob[i] = hub_demand['mgk_result'].p_cran
                    self.mgk_utilisation[i] = hub_demand['mgk_result'].utilisation
                
                self.order_queues[i] += new_orders
                self.episode_orders_total += new_orders
                self.queue_wait_time[i] += new_orders * self.step_minutes

    
    def _fulfill_orders(self) -> None:
        """
        Fulfill pending orders using available idle drones.
        Uses a pool of available drones across all hubs for flexibility.
        """
        
        for hub_idx in self.active_hub_indices:
            pending_orders = int(self.order_queues[hub_idx])
            if pending_orders <= 0:
                continue

            idle_drones = self._idle_drones_at_hub(hub_idx)
            orders_to_fulfill = min(len(idle_drones), pending_orders)
            if orders_to_fulfill <= 0:
                continue

            for drone in idle_drones[:orders_to_fulfill]:
                drone.in_flight = True
                drone.status = 'delivering'
                drone.busy_steps_remaining = self.delivery_duration_steps

            self.order_queues[hub_idx] -= orders_to_fulfill
            self.fleet_state.orders_fulfilled_this_step += orders_to_fulfill
            self.episode_orders_fulfilled += orders_to_fulfill
    
    def _update_fleet_states(self) -> None:
        """
        Update drone states: battery drain, charging, etc.
        Simplified: assume deliveries take 5 minutes, drones return to hub.
        """
        
        for drone in self.fleet_state.drones:
            if drone.in_flight:
                drone.busy_steps_remaining = max(0, drone.busy_steps_remaining - 1)
                drone.battery_level = max(0.0, drone.battery_level - 0.01 * self.step_minutes)
                if drone.busy_steps_remaining == 0:
                    drone.in_flight = False
                    drone.status = 'idle'
            elif drone.status == 'idle' and drone.battery_level < 1.0:
                drone.battery_level = min(1.0, drone.battery_level + 0.02 * self.step_minutes)
    
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
        obs[self.num_hubs:2*self.num_hubs] = np.clip(
            self.order_queues / QUEUE_OBSERVATION_CAP,
            0,
            1,
        )
        
        # Utilization per hub
        obs[2*self.num_hubs:3*self.num_hubs] = self.fleet_state.utilization_per_hub
        
        # Meal-time features
        meal_features = DemandGenerator.get_meal_time_features(self.current_hour)
        obs[27:31] = meal_features
        
        # Battery per hub
        obs[31:31+self.num_hubs] = self.fleet_state.battery_per_hub
        
        # Time sin/cos
        obs[40] = np.sin(2 * np.pi * self.current_hour / TIME_ENCODING_PERIOD_HOURS)
        obs[41] = np.cos(2 * np.pi * self.current_hour / TIME_ENCODING_PERIOD_HOURS)
        
        return obs
    
    def _compute_reward(self) -> float:
        """
        Multi-objective reward function — v2 (fixed reward saturation).

        Changes from v1
        ---------------
        1. Queue penalty is capped at fleet_size × 10 so a 900-order backlog
           does not produce a −9 000/step signal that drowns all other gradients.
           The agent can still detect "bad" vs "worse" within the cap range.

        2. Starved-hub penalty: −50 for every active hub that simultaneously
           has pending orders AND zero idle drones.  This gives a sparse,
           per-hub signal that directly incentivises pre-positioning before
           demand peaks arrive.

        Components
        ----------
        1. Fulfillment bonus  : +50 per order fulfilled this step
        2. Queue penalty      : −10 per queued order, capped at fleet_size × 10
        3. Starved-hub penalty: −50 per hub with queue > 3 AND idle == 0
        4. Craning penalty    : −200 per craning drone
        5. Dead-head cost     : −5 per dead-heading drone
        6. Idle bonus         : +10 × (idle − 5) / fleet_size  (if idle > 5)
        """
        fulfillment_bonus_raw = FULFILLMENT_BONUS * self.fleet_state.orders_fulfilled_this_step

        # Capped queue penalty — prevents saturation at large backlogs.
        total_queue_length = float(np.sum(self.order_queues))
        queue_cap          = float(self.fleet_size * QUEUE_PENALTY_CAP_MULTIPLIER)
        queue_penalty_raw  = -QUEUE_PENALTY_PER_ORDER * min(total_queue_length, queue_cap)

        # Per-hub starvation penalty — rewards pre-positioning.
        starved_hubs = sum(
            1 for i in self.active_hub_indices
            if self.order_queues[i] > STARVED_HUB_QUEUE_THRESHOLD and self.fleet_state.idle_per_hub[i] == 0
        )
        starved_penalty_raw = -STARVED_HUB_PENALTY * starved_hubs

        craning_penalty_raw  = -CRANING_PENALTY * self.fleet_state.drones_craning
        deadhead_penalty_raw = -DEADHEAD_PENALTY * self.fleet_state.drones_deadheading

        total_idle    = float(np.sum(self.fleet_state.idle_per_hub))
        idle_bonus_raw = 0.0
        if total_idle > IDLE_BONUS_THRESHOLD:
            idle_bonus_raw = IDLE_BONUS_SCALE * (total_idle - IDLE_BONUS_THRESHOLD) / self.fleet_size

        raw_total = (
            fulfillment_bonus_raw
            + queue_penalty_raw
            + starved_penalty_raw
            + craning_penalty_raw
            + deadhead_penalty_raw
            + idle_bonus_raw
        )

        reward = raw_total / REWARD_NORMALIZATION
        self.last_reward_components = {
            "fulfillment_bonus":  fulfillment_bonus_raw  / REWARD_NORMALIZATION,
            "queue_penalty":      queue_penalty_raw       / REWARD_NORMALIZATION,
            "starved_penalty":    starved_penalty_raw     / REWARD_NORMALIZATION,
            "craning_penalty":    craning_penalty_raw     / REWARD_NORMALIZATION,
            "deadhead_penalty":   deadhead_penalty_raw    / REWARD_NORMALIZATION,
            "idle_bonus":         idle_bonus_raw          / REWARD_NORMALIZATION,
            "total":              reward,
            "queue_length":       total_queue_length,
            "starved_hubs":       float(starved_hubs),
            "orders_fulfilled_this_step":     float(self.fleet_state.orders_fulfilled_this_step),
            "deadheading_drones_this_step":   float(self.fleet_state.drones_deadheading),
            "idle_drones":                    total_idle,
        }

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
