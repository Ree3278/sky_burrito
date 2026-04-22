"""RL environment settings for fleet training and inference."""

from settings.hub_sizing import MGK_P_CRAN_TARGET, MGK_UTIL_CAP

VIABLE_ROUTES = [
    ("Hub 11", "Hub 9", 2.40),
    ("Hub 9", "Hub 11", 2.40),
    ("Hub 10", "Hub 6", 2.44),
    ("Hub 1", "Hub 9", 2.25),
    ("Hub 9", "Hub 1", 2.25),
    ("Hub 11", "Hub 2", 2.18),
    ("Hub 6", "Hub 10", 2.44),
    ("Hub 2", "Hub 11", 2.18),
    ("Hub 2", "Hub 1", 2.14),
    ("Hub 9", "Hub 6", 2.29),
    ("Hub 3", "Hub 6", 2.18),
    ("Hub 1", "Hub 2", 2.14),
    ("Hub 6", "Hub 9", 2.29),
    ("Hub 10", "Hub 11", 2.14),
    ("Hub 11", "Hub 10", 2.14),
    ("Hub 6", "Hub 3", 2.18),
    ("Hub 7", "Hub 1", 1.87),
    ("Hub 5", "Hub 6", 1.89),
    ("Hub 1", "Hub 7", 1.87),
    ("Hub 2", "Hub 6", 1.91),
]

ACTIVE_HUBS = [
    "Hub 1", "Hub 2", "Hub 3", "Hub 5", "Hub 6",
    "Hub 7", "Hub 9", "Hub 10", "Hub 11",
]

DEADHEAD_BATTERY_REQUIRED = {
    "Hub 1": 0.15,
    "Hub 2": 0.15,
    "Hub 3": 0.15,
    "Hub 5": 0.20,
    "Hub 6": 0.15,
    "Hub 7": 0.20,
    "Hub 9": 0.15,
    "Hub 10": 0.20,
    "Hub 11": 0.15,
}

REBALANCE_ENABLED_HOURS = [
    (7.0, 9.0),
    (11.5, 13.5),
    (15.0, 17.0),
    (18.0, 20.0),
]

CONTINUOUS_REBALANCING = True

MEAL_MULTIPLIERS = {
    "breakfast": {"start": 7.0, "peak": 8.0, "end": 9.0, "multiplier": 1.5},
    "lunch": {"start": 11.5, "peak": 12.5, "end": 13.5, "multiplier": 2.2},
    "snack": {"start": 15.0, "peak": 16.0, "end": 17.0, "multiplier": 1.3},
    "dinner": {"start": 18.0, "peak": 19.0, "end": 20.0, "multiplier": 2.0},
}

DEFAULT_DEMAND_VARIABILITY = "meal_time_peaks"
DELIVERY_DURATION_MINUTES = 3.0
GHOST_HEARTBEAT_MINUTES = 5.0

MGK_MEAN_SERVICE_MIN = 3.0
DEMAND_BASELINE_MULTIPLIER = 0.3

ACTION_MIN = -5.0
ACTION_MAX = 5.0
QUEUE_OBSERVATION_CAP = 50.0
TIME_ENCODING_PERIOD_HOURS = 24.0

FULFILLMENT_BONUS = 50.0
QUEUE_PENALTY_PER_ORDER = 10.0
QUEUE_PENALTY_CAP_MULTIPLIER = 10.0
STARVED_HUB_QUEUE_THRESHOLD = 3.0
STARVED_HUB_PENALTY = 50.0
CRANING_PENALTY = 200.0
DEADHEAD_PENALTY = 5.0
IDLE_BONUS_THRESHOLD = 5.0
IDLE_BONUS_SCALE = 10.0
REWARD_NORMALIZATION = 100.0
