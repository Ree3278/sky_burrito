"""
Carbon footprint analysis: Drone vs Uber ground delivery.

CO2 Emissions Methodology
─────────────────────────

DRONE:
  CO2 = energy_wh × grid_co2_per_kwh / 1000
  
  Grid carbon intensity (SF): 
    • 2026 estimate: ~150 g CO2/kWh (highly renewable grid)
    • Reference: California 2025 average ~200 g CO2/kWh
    • Source: CARB, ISO data

UBER (Gas-powered car):
  CO2 = distance_miles × fuel_economy_mpg^-1 × gas_co2_per_gallon
  
  Typical assumptions:
    • Fuel economy: 30 mpg (mixed urban)
    • CO2 per gallon gasoline: 8.887 kg CO2 (EPA)
    • Idle burn: 0.5 L/hour = ~0.1 gal/hour

COMPARISON:
  Drone CO2 << Car CO2 (typically 50-100× lower)
"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class CarbonResult:
    """CO2 emissions for a delivery route."""
    
    # Drone metrics
    drone_energy_wh: float           # Battery consumption
    drone_co2_kg: float              # CO2 equivalent (kg)
    drone_co2_g: float               # CO2 equivalent (grams)
    
    # Ground (Uber) metrics
    ground_distance_miles: float     # Road distance
    ground_idle_time_hours: float    # Time stuck in traffic
    ground_co2_kg: float             # CO2 equivalent (kg)
    ground_co2_g: float              # CO2 equivalent (grams)
    
    # Comparison
    co2_saved_kg: float              # ground - drone
    co2_saved_g: float               # ground - drone
    co2_reduction_pct: float         # % reduction with drone


# Grid carbon intensity (g CO2 per kWh)
# SF has one of cleanest grids in US due to hydro + renewable percentage
GRID_CO2_PER_KWH_G = 150.0  # g/kWh (conservative 2026 estimate)

# Gasoline emissions
GASOLINE_CO2_PER_GALLON_KG = 8.887  # kg/gal (EPA standard)

# Car parameters
CAR_FUEL_ECONOMY_MPG = 30.0  # mixed urban driving
CAR_IDLE_BURN_GAL_PER_HOUR = 0.1  # 0.5 L/hr = ~0.1 gal/hr


def calculate_drone_carbon(energy_wh: float) -> Dict[str, float]:
    """
    Calculate CO2 emissions for drone delivery.
    
    Parameters
    ----------
    energy_wh : float
        Energy consumed (Wh)
    
    Returns
    -------
    dict with:
        'energy_kwh': float
        'co2_g': float (grams)
        'co2_kg': float (kilograms)
    """
    energy_kwh = energy_wh / 1000
    co2_g = energy_kwh * GRID_CO2_PER_KWH_G
    co2_kg = co2_g / 1000
    
    return {
        'energy_kwh': energy_kwh,
        'co2_g': co2_g,
        'co2_kg': co2_kg,
    }


def calculate_ground_carbon(
    distance_miles: float,
    travel_time_hours: float,
    idle_time_hours: float = 0,
) -> Dict[str, float]:
    """
    Calculate CO2 emissions for Uber ground delivery.
    
    Parameters
    ----------
    distance_miles : float
        Road distance driven
    travel_time_hours : float
        Time actually moving
    idle_time_hours : float
        Time stuck in traffic (engine running)
    
    Returns
    -------
    dict with:
        'driving_co2_kg': float (from movement)
        'idling_co2_kg': float (from sitting in traffic)
        'total_co2_kg': float
        'total_co2_g': float
    """
    # Driving emissions
    gallons_consumed = distance_miles / CAR_FUEL_ECONOMY_MPG
    driving_co2_kg = gallons_consumed * GASOLINE_CO2_PER_GALLON_KG
    
    # Idling emissions
    idling_co2_kg = idle_time_hours * CAR_IDLE_BURN_GAL_PER_HOUR * GASOLINE_CO2_PER_GALLON_KG
    
    # Total
    total_co2_kg = driving_co2_kg + idling_co2_kg
    total_co2_g = total_co2_kg * 1000
    
    return {
        'driving_co2_kg': driving_co2_kg,
        'idling_co2_kg': idling_co2_kg,
        'total_co2_kg': total_co2_kg,
        'total_co2_g': total_co2_g,
    }


def calculate_carbon_savings(
    drone_energy_wh: float,
    ground_distance_miles: float,
    ground_idle_time_hours: float = 0,
) -> CarbonResult:
    """
    Compare carbon footprint: drone vs ground delivery.
    
    Parameters
    ----------
    drone_energy_wh : float
        Energy used by drone (Wh)
    ground_distance_miles : float
        Distance driven by car (miles)
    ground_idle_time_hours : float
        Time idle in traffic (hours)
    
    Returns
    -------
    CarbonResult with full comparison
    """
    drone = calculate_drone_carbon(drone_energy_wh)
    ground = calculate_ground_carbon(
        ground_distance_miles,
        travel_time_hours=0,  # Not used in calculation
        idle_time_hours=ground_idle_time_hours,
    )
    
    co2_saved_kg = ground['total_co2_kg'] - drone['co2_kg']
    co2_saved_g = co2_saved_kg * 1000
    
    if ground['total_co2_kg'] > 0:
        reduction_pct = (co2_saved_kg / ground['total_co2_kg']) * 100
    else:
        reduction_pct = 0
    
    return CarbonResult(
        drone_energy_wh     = drone_energy_wh,
        drone_co2_kg        = drone['co2_kg'],
        drone_co2_g         = drone['co2_g'],
        ground_distance_miles = ground_distance_miles,
        ground_idle_time_hours = ground_idle_time_hours,
        ground_co2_kg       = ground['total_co2_kg'],
        ground_co2_g        = ground['total_co2_g'],
        co2_saved_kg        = co2_saved_kg,
        co2_saved_g         = co2_saved_g,
        co2_reduction_pct   = reduction_pct,
    )
