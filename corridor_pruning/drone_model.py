"""
Drone flight time and energy model for a single corridor.

Physics
-------
Total flight time:
    t_total = t_climb + t_cruise + t_descend

    where:
        t_climb   = obstacle_height_m / CLIMB_SPEED_MS
        t_cruise  = straight_line_m / CRUISE_SPEED_MS
        t_descend = obstacle_height_m / DESCENT_SPEED_MS

Total energy (Wh):
    E_total = E_climb + E_cruise

    E_climb  = (m * g * h) / (eta * 3600)      # potential energy / motor efficiency
    E_cruise = P_cruise * (straight_line_m / CRUISE_SPEED_MS) / 3600

Known unknowns
--------------
- obstacle_height_m is NOT computed here. It requires a spatial intersection of
  the flight-path LineString against the buildings GeoDataFrame — see pruning.py.
  Until that data is available, callers pass it explicitly or use the
  ASSUMED_CRUISE_ALTITUDE_M fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Drone hardware parameters (DJI Matrice 350 RTK class) ───────────────────
# ⚠ These are defaults. Override via DroneSpec for sensitivity analysis.

DRONE_MASS_KG       = 9.0     # total take-off weight including payload
CRUISE_SPEED_MS     = 15.0    # horizontal cruise speed, m/s (~54 km/h)
CLIMB_SPEED_MS      = 3.0     # vertical climb speed, m/s
DESCENT_SPEED_MS    = 2.0     # vertical descent speed, m/s
MOTOR_EFFICIENCY    = 0.75    # fraction of electrical energy converted to lift
CRUISE_POWER_W      = 350.0   # power draw at cruise, watts
GRAVITY_MS2         = 9.81

# Safety buffer added on top of the tallest obstacle on each route
OBSTACLE_SAFETY_BUFFER_M = 50.0

# Fallback cruise altitude when obstacle data is unavailable
ASSUMED_CRUISE_ALTITUDE_M = 120.0  # ← used only when obstacle_height_m is None


@dataclass
class DroneSpec:
    mass_kg:          float = DRONE_MASS_KG
    cruise_speed_ms:  float = CRUISE_SPEED_MS
    climb_speed_ms:   float = CLIMB_SPEED_MS
    descent_speed_ms: float = DESCENT_SPEED_MS
    motor_efficiency: float = MOTOR_EFFICIENCY
    cruise_power_w:   float = CRUISE_POWER_W


@dataclass
class DroneResult:
    cruise_altitude_m: float   # actual altitude flown (obstacle + buffer, or assumed)
    climb_time_s:      float
    cruise_time_s:     float
    descend_time_s:    float
    total_time_s:      float
    climb_energy_wh:   float
    cruise_energy_wh:  float
    descend_energy_wh: float   # gravitational assist: smaller than climb
    total_energy_wh:   float
    climb_cost_usd:    float   # Component: ascent electricity
    cruise_cost_usd:   float   # Component: horizontal flight
    descend_cost_usd:  float   # Component: descent (minimal, gravity helps)
    used_fallback_altitude: bool
    total_cost_usd:    float   # Total: climb + cruise + descend


def estimate_drone(
    straight_line_m: float,
    obstacle_height_m: Optional[float] = None,
    spec: DroneSpec = DroneSpec(),
) -> DroneResult:
    """
    Estimate drone flight time, energy, and cost for one corridor.

    Parameters
    ----------
    straight_line_m : float
        Haversine distance between origin and destination hubs.
    obstacle_height_m : float or None
        Tallest building directly under the flight path.
        When None, ASSUMED_CRUISE_ALTITUDE_M is used as a fallback and the
        result is flagged with used_fallback_altitude=True.
        ⚠ Provide real values from buildings.geojson for accurate scoring.
    spec : DroneSpec
        Hardware parameters. Defaults to DJI Matrice 350 RTK class values.

    Returns
    -------
    DroneResult with total_cost_usd calculated from energy consumption
    """
    used_fallback = obstacle_height_m is None
    if used_fallback:
        cruise_alt = ASSUMED_CRUISE_ALTITUDE_M
    else:
        cruise_alt = obstacle_height_m + OBSTACLE_SAFETY_BUFFER_M

    climb_time_s   = cruise_alt / spec.climb_speed_ms
    cruise_time_s  = straight_line_m / spec.cruise_speed_ms
    descend_time_s = cruise_alt / spec.descent_speed_ms
    total_time_s   = climb_time_s + cruise_time_s + descend_time_s

    # E_climb = mgh / (η × 3600 J/Wh)
    climb_energy_wh  = (spec.mass_kg * GRAVITY_MS2 * cruise_alt) / (spec.motor_efficiency * 3600)
    cruise_energy_wh = spec.cruise_power_w * (cruise_time_s / 3600)
    
    # Descent with gravity assist: ~25% of climb energy (rotors mainly stabilizing)
    descend_energy_wh = climb_energy_wh * 0.25
    
    total_energy_wh  = climb_energy_wh + cruise_energy_wh + descend_energy_wh

    # Calculate cost based on electricity consumption (SF grid: $0.12/kWh)
    electricity_cost_per_kwh = 0.12
    climb_cost_usd = (climb_energy_wh / 1000) * electricity_cost_per_kwh
    cruise_cost_usd = (cruise_energy_wh / 1000) * electricity_cost_per_kwh
    descend_cost_usd = (descend_energy_wh / 1000) * electricity_cost_per_kwh
    battery_cost = climb_cost_usd + cruise_cost_usd + descend_cost_usd
    
    # Maintenance cost per mile (~$0.016/mile for DJI Matrice 350 RTK)
    maintenance_cost_per_mile = 0.016
    distance_miles = straight_line_m / 1609.34
    maintenance_cost = distance_miles * maintenance_cost_per_mile
    
    # Total cost to operator
    total_cost_usd = battery_cost + maintenance_cost

    return DroneResult(
        cruise_altitude_m      = cruise_alt,
        climb_time_s           = climb_time_s,
        cruise_time_s          = cruise_time_s,
        descend_time_s         = descend_time_s,
        total_time_s           = total_time_s,
        climb_energy_wh        = climb_energy_wh,
        cruise_energy_wh       = cruise_energy_wh,
        descend_energy_wh      = descend_energy_wh,
        total_energy_wh        = total_energy_wh,
        climb_cost_usd         = climb_cost_usd,
        cruise_cost_usd        = cruise_cost_usd,
        descend_cost_usd       = descend_cost_usd,
        used_fallback_altitude = used_fallback,
        total_cost_usd         = total_cost_usd,
    )
