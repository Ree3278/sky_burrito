"""Pipeline-level tunables for pruning, sizing, and simulation setup."""

DEFAULT_CORRIDOR_SIM_HOUR: int = 19
DEFAULT_MIN_TIME_DELTA_S: int = 120
DEFAULT_MIN_DEMAND_WEIGHT: int = 100_000

DEFAULT_PRUNED_CORRIDOR_COUNT: int = 20
DEFAULT_SIMULATION_CORRIDOR_COUNT: int = DEFAULT_PRUNED_CORRIDOR_COUNT

NETWORK_PEAK_ORDERS_PER_HOUR: float = 200.0
# Ratio of peak-hour volume to the flat average used above.
# Friday 7–9 PM in SF food delivery is ~2–3× the daily average.
# ⚠ Replace with empirical peak factor from order data.
PEAK_MULTIPLIER: float = 2.2
DEFAULT_DEMAND_SCALE: float = 1.0
