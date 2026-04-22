# Sky Burrito

Sky Burrito is a data-driven prototype for a hub-to-hub drone delivery network in San Francisco's Mission–Noe Valley corridor. The repo now has a stable top-level CLI, a persisted simulation setup pipeline, a live Streamlit digital twin, and a PPO-based fleet rebalancing stack for the active 9-hub network.

## What the Project Does

The project models one narrow thesis: drones are only operationally interesting on corridors where straight-line flight meaningfully beats real ground delivery friction. The pipeline therefore moves through four stages:

1. Raw city-data ingest and hub siting
2. Corridor pruning and ranking
3. Hub sizing with M/G/k queueing
4. Live simulation with finite fleet dynamics and optional PPO rebalancing

The repo is core-first and code-first now; the notebooks are historical references, not the main entrypoint.

## Repo Shape

- `main.py` is the stable CLI façade.
- `cli/` holds parser and command implementations.
- `corridor_pruning/` scores hub-to-hub corridors on time, cost, energy, and CO2.
- `hub_sizing/` converts shortlisted demand into pad and battery-bay requirements.
- `simulation/` contains the persisted setup model, runtime builders, finite fleet, dispatcher, registry, RL environment, RL bridge, and Streamlit app.
- `settings/` holds tunables and paths.
- `testing/` contains regression and refactor-seam tests.

Within `simulation/`, the recent refactor split the core responsibilities:

- `environment.py` is a compatibility façade.
- `setup_models.py`, `setup_builders.py`, and `setup_io.py` separate dataclasses, assembly, and persistence.
- `app_support/` separates Streamlit runtime/state helpers from rendering helpers.
- `rl_schema.py` holds the shared 42D observation contract used by both the training env and the live RL bridge.
- `allocation.py` provides the shared largest-remainder integer allocator used by fleet seeding and deterministic rebalancing.

## Current Runtime Model

### Corridor pruning

The pruning stage evaluates all directed hub pairs and keeps the top-ranked corridors that clear minimum time and demand thresholds. It currently uses:

- Real building obstacle heights when `data/Building_Footprints_*.csv` is available
- Physics-based drone energy and cost estimates
- Uber-style ground delivery economics
- CO2 savings in the composite score

Still-real limitation:

- The ground model is still stubbed for road routing and traffic. OSMnx wiring is not complete yet, so `used_stubs` remains meaningful.

### Simulation

The live simulator models:

- Finite physical drones
- Per-hub idle pools and queued orders
- Drone state machine: `TAKEOFF -> CRUISE -> LANDING -> COOLDOWN`, with `CRANING` when destination pads are full
- NHPP demand with meal-time shaping
- Hub pad occupancy and saturation metrics
- Cross-hub fallback when an origin hub is empty but another viable origin can serve the same destination

### RL

The PPO stack is active in two places:

- `simulation/rl_fleet_env.py` for training and offline evaluation
- `simulation/rl_bridge.py` for the live Streamlit app

The live app already wires the RL bridge into the registry. Rebalancing still uses inventory-style instant repositioning inside `FleetPool`; payload flights remain the only visible flights on the map.

## Data Inputs

Place the raw CSVs under `data/`:

- `Registered_Business_Locations_-_San_Francisco_20260410.csv`
- `Building_Footprints_20260410.csv`
- `San_Francisco_Land_Use_-_2023_20260410.csv`

Committed GeoJSON files in the repo root are derived artifacts.

## Setup

```bash
uv sync --dev
```

If you already have the project environment synced, the key verification commands are:

```bash
uv run pytest -q testing
uv run ruff check .
```

## Entrypoints

```bash
# 1. Run siting and chart generation
uv run python main.py siting --skip-street-network

# Backward-compatible root invocation
uv run python main.py --hubs 8 --skip-street-network

# 2. Print the current corridor shortlist
uv run python main.py corridors --top-n 20 --sim-hour 19

# 3. Build and persist the simulation setup
uv run python main.py sizing --top-n 10 --fleet-size 30

# 4. Launch the Streamlit digital twin
uv run python main.py simulate
```

You can still launch the app directly:

```bash
uv run streamlit run simulation/app.py
```

## Verification Status

The refactored core stack is currently verified with:

- `python -m compileall` over `cli/`, `simulation/`, `testing/`, and `main.py`
- `pytest` across the full `testing/` suite
- `ruff check` across `cli`, `simulation`, `testing`, and `main.py`

Recent regression coverage now includes:

- CLI backward compatibility
- Setup save/load roundtrip
- Shared allocation behavior
- Shared RL observation contract
- Registry fallback and queue-drain behavior

## Known Gaps

- Ground routing still uses a stub model instead of full OSMnx travel times
- `corridor_pruning.pruning` still reports stub usage until the ground model is replaced
- The live RL bridge uses instant pool rebalancing rather than visible dead-head drone flights
- Some long-form summary markdown files are historical and were intentionally left untouched in this refactor pass
