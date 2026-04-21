"""
Rebalancing strategies for the Sky Burrito drone fleet.

Ghost Heuristic
---------------
A pressure-based dead-head rebalancing layer that sits alongside the
trained PPO agent. It identifies surplus hubs (drones > target) and
deficit hubs (orders > drones), then directly teleports drones from
donors to recipients using the shortest viable flight path.

The heuristic fires on a configurable heartbeat (default: every 5
simulated minutes) and is suppressed during the dinner-rush peak
(18:00–20:00) to keep every drone available for real revenue orders.

Usage
-----
    from rebalancing import GhostHeuristic, GhostConfig

    config = GhostConfig(heartbeat_steps=5, pressure_threshold=2.0)
    ghost = GhostHeuristic(hub_names=ACTIVE_HUBS, viable_routes=VIABLE_ROUTES, config=config)
"""

from .ghost_logic import GhostHeuristic, GhostConfig, GhostMove

__all__ = ["GhostHeuristic", "GhostConfig", "GhostMove"]
