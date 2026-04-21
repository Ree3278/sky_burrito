"""
Ghost Heuristic — pressure-based dead-head rebalancing for the Sky Burrito fleet.

Terminology
-----------
Ghost Move
    A dead-head flight dispatched by this heuristic (not by the RL agent).
    The drone carries no payload and flies directly from a Donor hub to a
    Recipient hub. It is called "ghost" because it originates not from a
    real customer order but from a systemic supply-demand imbalance signal.

Hub Pressure
    P_i = idle_i − queue_i − T_i

    where T_i is the target idle inventory for hub i.
    P_i > 0 : surplus (donor candidate)
    P_i < 0 : deficit (recipient candidate)

Target Inventory T_i
    Proportional to the hub's base arrival rate λ_i, scaled to fleet_size.
    Represents the "fair share" of idle drones the hub needs to absorb its
    expected demand without queueing.

Four-Phase Design
-----------------
Phase 1 — Hub Pressure Metrics   → compute_target_inventory / compute_pressure
Phase 2 — Donor–Recipient Match  → match_donors_to_recipients
Phase 3 — Environment Hook       → executed by DroneFleetEnv._execute_ghost_heuristic()
Phase 4 — Guardrails             → battery_floor, dinner suppression, craning check
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GhostConfig:
    """
    Tunable parameters for the ghost heuristic.

    heartbeat_steps : int
        How often the heuristic fires, expressed in environment steps.
        At sim_speedup=60 (1 min / step), 5 steps = 5 simulated minutes.
        At sim_speedup=1 (60 min / step), set this to 1.

    pressure_threshold : float
        Minimum absolute pressure |P_i| before a hub is treated as a
        donor or recipient. Lower values = more aggressive rebalancing.
        Recommended: 2.0 (avoids micro-moves for ±1 drone fluctuations).

    battery_floor : float
        Minimum state-of-charge (0–1) required for a drone to be eligible
        for a ghost dead-head flight. Enforces Phase 4 battery guardrail.
        Default: 0.30 (30 % SOC floor).

    dinner_suppress_start / dinner_suppress_end : float
        Hour-of-day range during which ghost moves are suspended entirely.
        During the Friday dinner rush (18:00–20:00) every available drone
        should serve real orders; no capacity should be tied up dead-heading.

    max_moves_per_heartbeat : int
        Upper bound on donor–recipient pairs resolved in one heartbeat tick.
        Prevents the heuristic from overwhelming the fleet with dead-heads
        during a cold start or after a long suppression window.

    max_drones_per_move : int
        Upper bound on drones committed to a single donor→recipient transfer.
        Keeps the move granular so the RL agent can still adapt.
    """
    heartbeat_steps: int       = 5
    pressure_threshold: float  = 2.0
    battery_floor: float       = 0.30
    dinner_suppress_start: float = 18.0
    dinner_suppress_end: float   = 20.0
    max_moves_per_heartbeat: int = 3
    max_drones_per_move: int     = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GhostMove:
    """A single dead-head rebalancing move produced by the heuristic."""
    donor_idx: int        # Index into ACTIVE_HUBS
    recipient_idx: int    # Index into ACTIVE_HUBS
    n_drones: int         # How many drones to send
    flight_time_min: float  # Estimated flight time (informational)

    def __repr__(self) -> str:
        return (
            f"GhostMove(donor={self.donor_idx} → recipient={self.recipient_idx}, "
            f"n={self.n_drones}, t={self.flight_time_min:.2f}min)"
        )


# ---------------------------------------------------------------------------
# Main heuristic class
# ---------------------------------------------------------------------------

class GhostHeuristic:
    """
    Pressure-based dead-head rebalancing heuristic.

    Intended to run as a co-pilot alongside the trained PPO agent — it handles
    the slow, structural tidal-flow drift that the RL agent cannot correct with
    its cyclic action routing, while the RL agent handles fast demand bursts.

    Parameters
    ----------
    hub_names : list[str]
        Ordered list of active hub names, e.g. ACTIVE_HUBS from rl_fleet_env.
        Index i in this list corresponds to index i in all per-hub arrays.
    viable_routes : list[tuple[str, str, float]]
        Pre-screened direct routes as (origin_hub, dest_hub, distance_km).
        Used to build the flight-time matrix; non-listed pairs fall back to
        Haversine straight-line distance.
    config : GhostConfig, optional
        Tunable parameters.  Defaults to GhostConfig().
    """

    # Base arrival rates (λ, orders/min) from DemandGenerator.HUB_PROFILES.
    # Used to compute proportional target inventories T_i.
    LAMBDA_BASE: Dict[str, float] = {
        "Hub 1":  1.5,
        "Hub 2":  1.2,
        "Hub 3":  1.8,
        "Hub 5":  0.8,
        "Hub 6":  1.4,
        "Hub 7":  1.0,
        "Hub 9":  2.2,
        "Hub 10": 1.1,
        "Hub 11": 1.6,
    }

    # Hub id → (lat, lon) — from corridor_pruning/hubs.py.
    # Kept here to avoid a circular import.
    HUB_COORDS: Dict[str, Tuple[float, float]] = {
        "Hub 1":  (37.765234, -122.430998),
        "Hub 2":  (37.751203, -122.414343),
        "Hub 3":  (37.764043, -122.416897),
        "Hub 5":  (37.764694, -122.422360),
        "Hub 6":  (37.751569, -122.436101),
        "Hub 7":  (37.751260, -122.419122),
        "Hub 9":  (37.753501, -122.410158),
        "Hub 10": (37.761275, -122.411260),
        "Hub 11": (37.761320, -122.435603),
    }

    CRUISE_SPEED_KMH: float = 54.0  # 15 m/s

    def __init__(
        self,
        hub_names: List[str],
        viable_routes: List[Tuple[str, str, float]],
        config: Optional[GhostConfig] = None,
    ) -> None:
        self.hub_names = hub_names
        self.viable_routes = viable_routes
        self.config = config or GhostConfig()

        # Pre-compute flight-time matrix [n_hubs × n_hubs] in minutes.
        self._flight_times: np.ndarray = self._build_flight_time_matrix()

        # Cumulative stats for monitoring.
        self.total_ghost_moves: int = 0
        self.total_ghost_drones: int = 0
        self.suppressed_ticks: int = 0

    # ------------------------------------------------------------------
    # Phase 1 — Hub Pressure Metrics
    # ------------------------------------------------------------------

    def compute_target_inventory(self, fleet_size: int) -> np.ndarray:
        """
        Compute per-hub target idle inventory T_i for the given fleet_size.

        T_i = round(λ_i / Σλ × fleet_size)

        The largest-remainder method ensures Σ T_i == fleet_size exactly.

        Returns
        -------
        np.ndarray[int], shape (n_hubs,)
        """
        n = len(self.hub_names)
        weights = np.array(
            [self.LAMBDA_BASE.get(h, 1.0) for h in self.hub_names],
            dtype=float,
        )
        proportions = weights / weights.sum()
        raw = proportions * fleet_size
        targets = raw.astype(int)

        remainder = fleet_size - targets.sum()
        if remainder > 0:
            # Distribute remaining slots to hubs with largest fractional parts.
            fractions = raw - targets
            top_indices = np.argsort(-fractions)[:remainder]
            targets[top_indices] += 1

        return targets

    def compute_pressure(
        self,
        idle_per_hub: np.ndarray,
        order_queues: np.ndarray,
        target_inventory: np.ndarray,
    ) -> np.ndarray:
        """
        Compute hub pressure vector P_i = idle_i − queue_i − T_i.

        Positive → surplus (donor candidate)
        Negative → deficit (recipient candidate)

        Parameters
        ----------
        idle_per_hub : np.ndarray[float], shape (n_hubs,)
        order_queues : np.ndarray[float], shape (n_hubs,)
        target_inventory : np.ndarray[int], shape (n_hubs,)

        Returns
        -------
        np.ndarray[float], shape (n_hubs,)
        """
        return idle_per_hub.astype(float) - order_queues.astype(float) - target_inventory.astype(float)

    # ------------------------------------------------------------------
    # Phase 2 — Donor–Recipient Matching
    # ------------------------------------------------------------------

    def match_donors_to_recipients(
        self,
        pressures: np.ndarray,
        active_hub_indices: Optional[List[int]] = None,
    ) -> List[GhostMove]:
        """
        Greedily match surplus hubs to deficit hubs by minimum flight time.

        Algorithm
        ---------
        1. Donors : hubs with P_i > pressure_threshold, sorted descending.
        2. Recipients: hubs with P_i < −pressure_threshold, sorted ascending.
        3. For each iteration up to max_moves_per_heartbeat:
           - Pick the (donor, recipient) pair with minimum flight time.
           - Commit min(surplus, deficit, max_drones_per_move) drones.
           - Decrement both pools; remove exhausted hubs.

        Parameters
        ----------
        pressures : np.ndarray[float], shape (n_hubs,)
        active_hub_indices : list[int] | None
            Restrict matching to active hubs only.  Defaults to all hubs.

        Returns
        -------
        List[GhostMove]
        """
        cfg = self.config
        indices = (
            active_hub_indices
            if active_hub_indices is not None
            else list(range(len(self.hub_names)))
        )

        # Build working surplus / deficit pools.
        donor_pool: Dict[int, float] = {
            i: float(pressures[i])
            for i in indices
            if pressures[i] > cfg.pressure_threshold
        }
        recipient_pool: Dict[int, float] = {
            i: float(-pressures[i])
            for i in indices
            if pressures[i] < -cfg.pressure_threshold
        }

        if not donor_pool or not recipient_pool:
            return []

        moves: List[GhostMove] = []

        for _ in range(cfg.max_moves_per_heartbeat):
            if not donor_pool or not recipient_pool:
                break

            # Find the (donor, recipient) pair with shortest flight time.
            best_time = float("inf")
            best_pair: Optional[Tuple[int, int]] = None

            for d_idx in donor_pool:
                for r_idx in recipient_pool:
                    t = self._flight_times[d_idx, r_idx]
                    if t < best_time:
                        best_time = t
                        best_pair = (d_idx, r_idx)

            if best_pair is None:
                break

            d_idx, r_idx = best_pair
            n = int(min(
                donor_pool[d_idx],
                recipient_pool[r_idx],
                cfg.max_drones_per_move,
            ))

            if n > 0:
                moves.append(GhostMove(
                    donor_idx=d_idx,
                    recipient_idx=r_idx,
                    n_drones=n,
                    flight_time_min=best_time,
                ))
                donor_pool[d_idx] -= n
                recipient_pool[r_idx] -= n

            # Prune exhausted pools.
            if donor_pool.get(d_idx, 0) <= cfg.pressure_threshold:
                donor_pool.pop(d_idx, None)
            if recipient_pool.get(r_idx, 0) <= cfg.pressure_threshold:
                recipient_pool.pop(r_idx, None)

        return moves

    # ------------------------------------------------------------------
    # Phase 4 — Guardrails
    # ------------------------------------------------------------------

    def should_suppress(self, hour: float) -> bool:
        """
        Return True if ghost moves should be suspended at this sim hour.

        Suppression window: dinner rush (default 18:00–20:00).
        Every available drone should serve real revenue orders during peak.
        """
        return self.config.dinner_suppress_start <= hour < self.config.dinner_suppress_end

    @staticmethod
    def recipient_is_safe(
        recipient_idx: int,
        utilization_per_hub: np.ndarray,
        util_ceiling: float = 0.85,
    ) -> bool:
        """
        Craning check (Phase 4): return False if the recipient hub is already
        heavily loaded.  Sending a drone to an overloaded hub risks craning
        (drone circles waiting for a landing pad) which carries a −200 penalty.

        Parameters
        ----------
        recipient_idx : int
        utilization_per_hub : np.ndarray[float], shape (n_hubs,)
            Fraction of drones at each hub that are currently busy (0–1).
        util_ceiling : float
            Utilisation above which the hub is considered unsafe.
        """
        return float(utilization_per_hub[recipient_idx]) < util_ceiling

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_flight_time_matrix(self) -> np.ndarray:
        """
        Build n_hubs × n_hubs flight-time matrix (minutes).

        Priority order per pair:
        1. VIABLE_ROUTES entry  — uses the verified corridor distance.
        2. Haversine fallback   — straight-line distance / cruise speed.

        Pairs with no direct viable route are not penalised with an
        artificial high cost — the drone can fly the Haversine path even
        if that corridor wasn't in the economic shortlist.
        """
        n = len(self.hub_names)
        hub_to_idx = {h: i for i, h in enumerate(self.hub_names)}

        # Initialise with Haversine-based defaults.
        matrix = np.zeros((n, n), dtype=float)
        for i, h1 in enumerate(self.hub_names):
            for j, h2 in enumerate(self.hub_names):
                if i == j:
                    continue
                coords1 = self.HUB_COORDS.get(h1)
                coords2 = self.HUB_COORDS.get(h2)
                if coords1 and coords2:
                    dist_km = self._haversine_km(*coords1, *coords2)
                else:
                    dist_km = 2.5  # Reasonable fallback for unknown hubs
                matrix[i, j] = (dist_km / self.CRUISE_SPEED_KMH) * 60.0

        # Overwrite with more accurate VIABLE_ROUTES distances where available.
        for origin, dest, distance_km in self.viable_routes:
            i = hub_to_idx.get(origin)
            j = hub_to_idx.get(dest)
            if i is not None and j is not None:
                matrix[i, j] = (distance_km / self.CRUISE_SPEED_KMH) * 60.0

        return matrix

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance in km between two (lat, lon) points."""
        R = 6_371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.asin(math.sqrt(min(1.0, a)))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def flight_time_summary(self) -> str:
        """Return a formatted view of the flight-time matrix (for debugging)."""
        lines = ["Flight-time matrix (minutes):"]
        header = "       " + "  ".join(f"{h:>7}" for h in self.hub_names)
        lines.append(header)
        for i, h in enumerate(self.hub_names):
            row = f"{h:>7}  " + "  ".join(
                f"{self._flight_times[i, j]:7.2f}" for j in range(len(self.hub_names))
            )
            lines.append(row)
        return "\n".join(lines)

    def pressure_summary(
        self,
        pressures: np.ndarray,
        target_inventory: np.ndarray,
        idle_per_hub: np.ndarray,
        order_queues: np.ndarray,
    ) -> str:
        """Return a readable pressure report for one timestep."""
        lines = [
            f"{'Hub':<8} {'Idle':>5} {'Queue':>6} {'Target':>7} {'Pressure':>9} {'Status':>10}"
        ]
        for i, h in enumerate(self.hub_names):
            p = pressures[i]
            status = (
                "DONOR ▲" if p > self.config.pressure_threshold
                else "DEFICIT ▼" if p < -self.config.pressure_threshold
                else "balanced"
            )
            lines.append(
                f"{h:<8} {int(idle_per_hub[i]):>5} {int(order_queues[i]):>6} "
                f"{int(target_inventory[i]):>7} {p:>9.1f} {status:>10}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from simulation.rl_fleet_env import ACTIVE_HUBS, VIABLE_ROUTES

    print("=== Ghost Heuristic — self test ===\n")

    gh = GhostHeuristic(hub_names=list(ACTIVE_HUBS), viable_routes=VIABLE_ROUTES)
    print(gh.flight_time_summary())
    print()

    # Simulate a post-dinner tidal state:
    # Hub 6 is a sink (accumulated drones), Hub 3 is dry
    idle_test = np.array([3., 2., 0., 1., 8., 1., 4., 2., 3.])  # Hub 3 (idx2)=0, Hub6(idx4)=8
    queue_test = np.array([2., 1., 4., 0., 0., 1., 3., 1., 2.])  # Hub 3 queue=4
    fleet_size = 30

    targets = gh.compute_target_inventory(fleet_size)
    pressures = gh.compute_pressure(idle_test, queue_test, targets)

    print(f"Fleet size: {fleet_size}")
    print(gh.pressure_summary(pressures, targets, idle_test, queue_test))
    print()

    moves = gh.match_donors_to_recipients(pressures)
    if moves:
        print(f"Ghost moves ({len(moves)}):")
        for m in moves:
            d_name = list(ACTIVE_HUBS)[m.donor_idx]
            r_name = list(ACTIVE_HUBS)[m.recipient_idx]
            print(f"  {d_name} → {r_name}  ×{m.n_drones}  ({m.flight_time_min:.2f} min)")
    else:
        print("No ghost moves needed.")

    print("\nDinner-rush suppression check:")
    print(f"  Hour 18.5 → suppress={gh.should_suppress(18.5)}")
    print(f"  Hour 21.0 → suppress={gh.should_suppress(21.0)}")
    print(f"  Hour 12.0 → suppress={gh.should_suppress(12.0)}")
