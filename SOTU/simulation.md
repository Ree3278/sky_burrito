# State of the Union — Simulation
**Date:** April 22, 2026  
**Module:** `simulation/`

## What This Layer Owns

The simulation stack converts the corridor shortlist and hub sizing outputs into a live Friday-evening digital twin. It owns:

- persisted setup artifacts for the active network
- runtime environment assembly
- finite-fleet order dispatch and queueing
- live Pydeck/Streamlit rendering
- PPO training, inference, and live rebalancing integration

## Current Architecture

The simulation package is now split by responsibility instead of centering everything in a few oversized files.

### Stable façades

- `simulation/environment.py`
  - compatibility façade for setup models, builders, and persistence
- `simulation/app.py`
  - stable Streamlit entrypoint

### Setup and runtime assembly

- `simulation/setup_models.py`
  - persisted setup dataclasses and runtime environment dataclasses
- `simulation/setup_builders.py`
  - build setup, build runtime environment, create registry
- `simulation/setup_io.py`
  - save/load/load-or-build setup JSON

### Live simulation core

- `simulation/fleet.py`
  - finite idle fleet and queued-order counts by hub
- `simulation/dispatcher.py`
  - NHPP request generation with meal-time demand shaping
- `simulation/drone.py`
  - payload-flight state machine
- `simulation/registry.py`
  - central runtime coordinator
- `simulation/registry_support.py`
  - routing fallback and pad-accounting helpers

### RL

- `simulation/rl_schema.py`
  - shared 42D observation contract and active-hub ordering
- `simulation/rl_fleet_env.py`
  - Gymnasium environment for PPO training/evaluation
- `simulation/rl_bridge.py`
  - live-app bridge from PPO policy to `FleetPool`

### Streamlit support

- `simulation/app_support/runtime.py`
  - cached environment/model loading and session-state control flow
- `simulation/app_support/views.py`
  - page styling, deck builders, metrics, and featured-route rendering

## Runtime Behavior

### Finite fleet

The simulator no longer spawns drones from nothing. `FleetPool` tracks:

- idle drones by hub
- queued orders by origin hub

When an order arrives:

1. registry tries the designated origin hub
2. if empty, registry may use a different viable origin hub with an idle drone
3. if no viable origin has inventory, the order queues at the original origin

When a drone completes cooldown:

1. it checks back into the destination hub
2. that destination hub's origin queue is drained immediately if demand is waiting

### Drone states

Live payload drones move through:

`TAKEOFF -> CRUISE -> LANDING -> COOLDOWN -> IDLE`

If destination pads are full, the drone enters:

`CRANING -> COOLDOWN`

### RL in the live app

The Streamlit app already wires the PPO bridge into registry creation. The bridge fires once per simulated minute and mutates `FleetPool` counts directly. That means:

- RL rebalancing is active in the app today
- payload flights remain visible
- rebalancing flights are not rendered as physical dead-head drones yet

## Verified Contracts

The refactor added or preserved tests for:

- setup JSON roundtrip
- shared RL observation schema
- registry fallback routing
- queue drain on destination checkin
- CLI backward compatibility

Current local verification commands:

```bash
uv run pytest -q testing
uv run ruff check .
```

## Real Gaps Still Open

- Live rebalancing is still pool-based, not flight-based
- Ground routing in the upstream pruning layer is still stubbed
- App behavior is stable, but the UI is still a single-page operational dashboard rather than a comparison workflow
- Phase 4 RL training remains optional work; the core training/evaluation stack is already wired
