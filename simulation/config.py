"""
Simulation configuration — time, physics, and visual constants.

All tunable knobs live here so the app and state machine never have
magic numbers scattered through them.
"""

# ── Time ─────────────────────────────────────────────────────────────────────

# 1 second of wall-clock time = TIME_MULTIPLIER seconds of simulation time.
# 60 → a 6-minute drone flight completes in 6 real seconds.
TIME_MULTIPLIER: float = 60.0

# How often the Streamlit loop redraws (real seconds between frames).
TICK_REAL_S: float = 0.25

# Simulation start time expressed as seconds past midnight.
# 18:00:00 = Friday 6 PM = start of the peak window.
SIM_START_S: float = 18 * 3600

# How long to simulate (sim-seconds). 3 hours = Friday 6–9 PM peak.
SIM_DURATION_S: float = 3 * 3600


# ── Map ──────────────────────────────────────────────────────────────────────

MAP_CENTER_LAT: float = 37.758
MAP_CENTER_LON: float = -122.422
MAP_ZOOM: float = 12.7
MAP_PITCH: int = 38   # degrees tilt for 3-D feel
MAP_BEARING: int = -8
MAP_STYLE: str = "light"


# ── Drone physics (mirrors drone_model.py defaults) ──────────────────────────

CRUISE_SPEED_MS:    float = 15.0
CLIMB_SPEED_MS:     float = 3.0
DESCENT_SPEED_MS:   float = 2.0
ASSUMED_ALTITUDE_M: float = 120.0   # fallback when obstacle height unknown


# ── Visual palette ───────────────────────────────────────────────────────────

# Drone dot colors by state  [R, G, B, A]
COLOR_IDLE     = [100, 100, 100, 180]
COLOR_TAKEOFF  = [255, 200,   0, 220]
COLOR_CRUISE   = [ 30, 160, 255, 230]
COLOR_LANDING  = [255, 140,   0, 220]
COLOR_COOLDOWN = [ 80, 200,  80, 180]
COLOR_CRANING  = [255,  30,  30, 255]   # red — the money shot

# Hub colors by tier
COLOR_HUB_HEAVY    = [220,  50,  50, 200]
COLOR_HUB_MODERATE = [230, 160,  30, 200]
COLOR_HUB_LIGHT    = [ 60, 180,  60, 200]

# Corridor arc color (dim; drones are the hero)
COLOR_CORRIDOR_ARC = [100, 180, 255,  60]

# Pad-occupancy heat color (used in hub ring overlay)
COLOR_PAD_BUSY  = [255,  80,  80, 200]
COLOR_PAD_FREE  = [ 80, 200,  80, 200]
