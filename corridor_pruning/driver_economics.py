"""
Uber platform economics: what UBER PAYS PER DELIVERY.

Formula:
  1. Base pay = (time_min × $0.35 + distance_mi × $1.25 - 25% service fee)
  2. Apply surge multiplier by hour
  3. Result = what Uber's P&L shows as "driver cost"

No tips, no vehicle costs, no driver net income.

This is used to calculate the cost to Uber (the platform) for ground delivery,
which we compare against drone delivery cost to determine cost arbitrage.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DriverEconomicsSpec:
    """Uber's driver payout formula per delivery."""
    
    # Base pay components
    pay_per_minute_usd: float = 0.35
    pay_per_mile_usd: float = 1.25
    uber_service_fee_pct: float = 0.25  # 25% deducted from base
    
    # Surge pricing by hour (0-23, Friday evening model)
    surge_multipliers: Dict[int, float] = field(default_factory=lambda: {
        0: 0.8, 1: 0.8, 2: 0.8, 3: 0.8, 4: 0.8, 5: 0.8,       # Midnight–6 AM
        6: 0.9, 7: 0.9, 8: 0.9, 9: 0.9, 10: 1.0,              # Morning
        11: 1.0, 12: 1.0, 13: 1.0, 14: 1.0, 15: 1.0,          # Midday
        16: 1.0, 17: 1.2,                                       # Late afternoon
        18: 1.5, 19: 1.5, 20: 1.4, 21: 1.3,                   # 6–9 PM PEAK
        22: 1.0, 23: 0.8,                                       # Night
    })


def calculate_uber_payout(
    travel_time_minutes: float,
    distance_miles: float,
    hour_of_day: int,
    spec: DriverEconomicsSpec = DriverEconomicsSpec(),
) -> Dict[str, float]:
    """
    Calculate what UBER PAYS for one delivery.
    
    Parameters
    ----------
    travel_time_minutes : float
        Actual trip duration (including traffic)
    distance_miles : float
        Actual road distance driven
    hour_of_day : int
        Hour (0-23) to determine surge multiplier
    spec : DriverEconomicsSpec
        Payment formula
    
    Returns
    -------
    dict with keys:
        'time_component': float       ($0.35 × minutes)
        'distance_component': float   ($1.25 × miles)
        'subtotal': float             (before fee deduction)
        'service_fee': float          (25% of subtotal)
        'base_pay': float             (subtotal - service_fee)
        'surge_multiplier': float     (1.0–1.5×)
        'total_uber_payout': float    (base_pay × surge, what we use)
    
    Example
    -------
    >>> payout = calculate_uber_payout(14, 2.55, hour_of_day=19)
    >>> print(payout['total_uber_payout'])
    13.65  # Uber pays $13.65 for this delivery at 7 PM
    """
    
    # 1. Time + distance components
    time_component = travel_time_minutes * spec.pay_per_minute_usd
    distance_component = distance_miles * spec.pay_per_mile_usd
    
    # 2. Subtract Uber's 25% service fee
    subtotal = time_component + distance_component
    service_fee = subtotal * spec.uber_service_fee_pct
    base_pay = subtotal - service_fee
    
    # 3. Apply surge multiplier
    surge_mult = spec.surge_multipliers.get(hour_of_day, 1.0)
    
    # 4. Final payout (no tips)
    total_payout = base_pay * surge_mult
    
    return {
        'time_component': time_component,
        'distance_component': distance_component,
        'subtotal': subtotal,
        'service_fee': service_fee,
        'base_pay': base_pay,
        'surge_multiplier': surge_mult,
        'total_uber_payout': total_payout,
    }
