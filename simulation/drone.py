"""
Drone agent — five-state state machine.

States
------
IDLE      Sitting at a hub pad. Waiting for a dispatch order.
TAKEOFF   Ascending vertically from hub altitude to cruise altitude.
CRUISE    Flying horizontally along the corridor LineString.
LANDING   Descending vertically into the destination hub.
COOLDOWN  On the pad: unload → battery swap → reload. Pad is occupied.
CRANING   In the air, circling, waiting for a pad to open at destination.
          This is the failure mode the M/G/k model is trying to prevent.

Position representation
-----------------------
(lat, lon) — updated every tick via Shapely interpolation on the corridor
LineString. Altitude is tracked separately for potential 3-D rendering.

Usage
-----
    drone = Drone(drone_id=1, corridor=c, cruise_altitude_m=120)
    while not drone.done:
        drone.move(dt_s)          # advance by dt seconds of sim time
        lat, lon = drone.position
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from corridor_pruning.corridors import Corridor

from .config import (
    ASSUMED_ALTITUDE_M,
    CLIMB_SPEED_MS,
    COLOR_COOLDOWN,
    COLOR_CRANING,
    COLOR_CRUISE,
    COLOR_IDLE,
    COLOR_LANDING,
    COLOR_TAKEOFF,
    CRUISE_SPEED_MS,
    DESCENT_SPEED_MS,
)


class DroneState(Enum):
    IDLE     = auto()
    TAKEOFF  = auto()
    CRUISE   = auto()
    LANDING  = auto()
    COOLDOWN = auto()
    CRANING  = auto()


# Seconds a drone spends in COOLDOWN (battery swap + reload).
# Mirrors service.py BATTERY_SWAP_S + margins.
COOLDOWN_S: float = 330.0

STATE_COLOR = {
    DroneState.IDLE:     COLOR_IDLE,
    DroneState.TAKEOFF:  COLOR_TAKEOFF,
    DroneState.CRUISE:   COLOR_CRUISE,
    DroneState.LANDING:  COLOR_LANDING,
    DroneState.COOLDOWN: COLOR_COOLDOWN,
    DroneState.CRANING:  COLOR_CRANING,
}

# Degrees per metre at SF latitude (approx)
_DEG_PER_M_LAT = 1 / 111_000
_DEG_PER_M_LON = 1 / (111_000 * math.cos(math.radians(37.76)))


@dataclass
class Drone:
    drone_id: int
    corridor: "Corridor"
    cruise_altitude_m: float = ASSUMED_ALTITUDE_M

    # Internal state
    state: DroneState         = field(default=DroneState.IDLE, init=False)
    altitude_m: float         = field(default=0.0, init=False)
    cruise_progress: float    = field(default=0.0, init=False)  # 0 → 1 along corridor
    cooldown_remaining_s: float = field(default=0.0, init=False)
    craning_s: float          = field(default=0.0, init=False)  # time spent craning

    # Whether destination pad was available on arrival
    pad_available: bool       = field(default=True, init=False)

    def __post_init__(self):
        self.state = DroneState.TAKEOFF

    # ── Position ─────────────────────────────────────────────────────────────

    @property
    def position(self) -> Tuple[float, float]:
        """Current (lat, lon). Interpolates along corridor during CRUISE."""
        if self.state in (DroneState.TAKEOFF, DroneState.COOLDOWN, DroneState.IDLE):
            return (self.corridor.origin.lat, self.corridor.origin.lon)
        if self.state in (DroneState.LANDING, DroneState.CRANING):
            return (self.corridor.destination.lat, self.corridor.destination.lon)
        if self.state == DroneState.CRUISE:
            return self._interpolate(self.cruise_progress)
        return (self.corridor.origin.lat, self.corridor.origin.lon)

    def _interpolate(self, t: float) -> Tuple[float, float]:
        """Linear interpolation along the corridor great-circle."""
        t = max(0.0, min(1.0, t))
        lat = self.corridor.origin.lat + t * (
            self.corridor.destination.lat - self.corridor.origin.lat
        )
        lon = self.corridor.origin.lon + t * (
            self.corridor.destination.lon - self.corridor.origin.lon
        )
        return (lat, lon)

    @property
    def color(self):
        return STATE_COLOR[self.state]

    @property
    def done(self) -> bool:
        """True once the drone has completed cooldown and is ready to redispatch."""
        return self.state == DroneState.IDLE and self.cooldown_remaining_s <= 0

    # ── State machine ─────────────────────────────────────────────────────────

    def move(self, dt_s: float, pad_free_at_dest: bool = True) -> None:
        """
        Advance the drone by dt_s simulation seconds.

        Parameters
        ----------
        dt_s             : simulation seconds elapsed since last tick
        pad_free_at_dest : True if the destination hub has a free pad.
                           If False on LANDING arrival, drone enters CRANING.
        """
        if self.state == DroneState.TAKEOFF:
            self.altitude_m += CLIMB_SPEED_MS * dt_s
            if self.altitude_m >= self.cruise_altitude_m:
                self.altitude_m = self.cruise_altitude_m
                self.state = DroneState.CRUISE

        elif self.state == DroneState.CRUISE:
            dist_per_tick = CRUISE_SPEED_MS * dt_s
            self.cruise_progress += dist_per_tick / self.corridor.straight_line_m
            if self.cruise_progress >= 1.0:
                self.cruise_progress = 1.0
                self.state = DroneState.LANDING
                self.altitude_m = self.cruise_altitude_m

        elif self.state == DroneState.LANDING:
            self.altitude_m -= DESCENT_SPEED_MS * dt_s
            if self.altitude_m <= 0.0:
                self.altitude_m = 0.0
                if pad_free_at_dest:
                    self.state = DroneState.COOLDOWN
                    self.cooldown_remaining_s = COOLDOWN_S
                else:
                    # No pad available — enter craning
                    self.state = DroneState.CRANING
                    self.altitude_m = 30.0   # holding altitude

        elif self.state == DroneState.CRANING:
            self.craning_s += dt_s
            # Retry every tick — registry will call move() again with updated pad status
            if pad_free_at_dest:
                self.state = DroneState.COOLDOWN
                self.cooldown_remaining_s = COOLDOWN_S
                self.altitude_m = 0.0

        elif self.state == DroneState.COOLDOWN:
            self.cooldown_remaining_s -= dt_s
            if self.cooldown_remaining_s <= 0:
                self.cooldown_remaining_s = 0.0
                self.state = DroneState.IDLE

    # ── Serialisation for Pydeck ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        lat, lon = self.position
        return {
            "drone_id":    self.drone_id,
            "lat":         lat,
            "lon":         lon,
            "altitude_m":  self.altitude_m,
            "state":       self.state.name,
            "color":       self.color,
            "origin_id":   self.corridor.origin.id,
            "dest_id":     self.corridor.destination.id,
            "progress":    round(self.cruise_progress, 3),
            "craning_s":   round(self.craning_s, 1),
        }
