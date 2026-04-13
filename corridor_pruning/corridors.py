"""
Generate and describe all candidate hub-to-hub corridors.

12 hubs → 132 directed pairs (12 × 11, no self-loops).
The pruning stage will filter these down to the ~20 highest-value routes.

Straight-line distance uses the Haversine formula, which is accurate enough
for the ~5 km scale of this corridor. Bearing is also computed so that
directional patterns (e.g., north-south vs east-west) can be analysed later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import permutations
from typing import List, Optional

from .hubs import Hub, HUBS

# Earth radius used in Haversine
_EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in metres between two WGS-84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial bearing (degrees, 0–360) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


@dataclass
class Corridor:
    """A directed hub-to-hub route candidate."""

    origin: Hub
    destination: Hub

    # Geometry
    straight_line_m: float = field(init=False)
    bearing_deg: float = field(init=False)

    # ── Fields populated by drone_model ─────────────────────────────
    # Max obstacle height (m) along the flight path — requires buildings data
    obstacle_height_m: Optional[float] = None   # ← MISSING: needs buildings GeoDataFrame

    # Estimated drone flight time (seconds)
    drone_time_s: Optional[float] = None

    # Estimated drone energy (Wh)
    drone_energy_wh: Optional[float] = None

    # ── Fields populated by ground_model ────────────────────────────
    # Actual road distance (m) from OSMnx shortest path
    road_distance_m: Optional[float] = None     # ← MISSING: needs OSMnx graph

    # Estimated ground transit time (seconds)
    ground_time_s: Optional[float] = None       # ← MISSING: needs OSMnx + traffic data

    # ── Derived scores (populated by pruning.score_corridor) ────────
    time_delta_s: Optional[float] = None        # ground_time_s - drone_time_s
    detour_ratio: Optional[float] = None        # road_distance_m / straight_line_m

    def __post_init__(self):
        self.straight_line_m = haversine_m(
            self.origin.lat, self.origin.lon,
            self.destination.lat, self.destination.lon,
        )
        self.bearing_deg = bearing_deg(
            self.origin.lat, self.origin.lon,
            self.destination.lat, self.destination.lon,
        )

    @property
    def label(self) -> str:
        return f"Hub {self.origin.id} → Hub {self.destination.id}"

    @property
    def demand_weight(self) -> int:
        """
        Combined supply–demand score for this corridor.
        Higher = more orders expected to flow on this route.
        """
        return self.origin.restaurants_nearby * self.destination.resunits_nearby

    @property
    def is_scoreable(self) -> bool:
        """True only when all time/energy fields have been populated."""
        return all(v is not None for v in [
            self.drone_time_s,
            self.ground_time_s,
            self.time_delta_s,
        ])

    def __repr__(self):
        base = f"{self.label}  {self.straight_line_m:.0f} m"
        if self.time_delta_s is not None:
            base += f"  Δt={self.time_delta_s:.0f}s"
        return base


def generate_corridors(hubs: List[Hub] = HUBS) -> List[Corridor]:
    """
    Return all directed hub-to-hub pairs (no self-loops).

    Parameters
    ----------
    hubs : list of Hub
        Defaults to the 12 hard-coded project hubs.

    Returns
    -------
    corridors : list of Corridor
        132 directed pairs, sorted by straight-line distance ascending.
    """
    corridors = [
        Corridor(origin=a, destination=b)
        for a, b in permutations(hubs, 2)
    ]
    corridors.sort(key=lambda c: c.straight_line_m)
    print(f"[corridors] Generated {len(corridors)} directed corridors.")
    return corridors
