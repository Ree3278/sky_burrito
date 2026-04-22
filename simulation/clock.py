"""
Simulation clock.

Tracks simulated time independently from wall-clock time.
Each call to tick() advances by TICK_REAL_S × TIME_MULTIPLIER simulation seconds.
"""

from __future__ import annotations

import time

from .config import SIM_START_S, TICK_REAL_S, TIME_MULTIPLIER


class SimClock:
    """
    Lightweight simulation clock.

    Attributes
    ----------
    sim_time_s : float
        Current simulation time in seconds past midnight (Friday).
    tick_sim_s : float
        Simulation seconds that pass per real-time tick.
    """

    def __init__(self, time_multiplier: float = TIME_MULTIPLIER):
        self.time_multiplier = time_multiplier
        self.tick_sim_s: float = TICK_REAL_S * time_multiplier
        self.sim_time_s: float = SIM_START_S
        self._wall_start: float = time.monotonic()

    def tick(self) -> float:
        """Advance simulation time by one tick. Returns new sim_time_s."""
        self.sim_time_s += self.tick_sim_s
        return self.sim_time_s

    @property
    def elapsed_sim_s(self) -> float:
        return self.sim_time_s - SIM_START_S

    @property
    def hhmm(self) -> str:
        """Human-readable simulated time, e.g. '18:42'."""
        total = int(self.sim_time_s)
        h = (total // 3600) % 24
        m = (total % 3600) // 60
        return f"{h:02d}:{m:02d}"

    def set_multiplier(self, multiplier: float) -> None:
        self.time_multiplier = multiplier
        self.tick_sim_s = TICK_REAL_S * multiplier

    def reset(self) -> None:
        self.sim_time_s = SIM_START_S
        self._wall_start = time.monotonic()
