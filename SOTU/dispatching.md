# State of the Union — Dispatching
**Date:** April 22, 2026  
**Modules:** `simulation/dispatcher.py`, `simulation/registry.py`, `simulation/fleet.py`

## What Dispatching Owns

Dispatching is the layer that turns a corridor shortlist into live order flow. It covers:

- order generation
- origin-side queueing
- drone assignment
- fallback routing when an origin hub is empty
- queue draining when drones return to service

## Current Model

### Demand generation

`Dispatcher` emits `DispatchRequest` objects, not drones. Demand is generated with a non-homogeneous Poisson process:

- baseline off-peak demand
- breakfast peak
- lunch peak
- snack peak
- dinner peak

The dispatcher samples from corridor demand weights and carries fractional arrivals between ticks so order volume stays numerically stable at high tick rates.

### Assignment rules

`DroneRegistry` applies dispatching in this order:

1. if the origin hub already has backlog, enqueue and preserve FIFO
2. otherwise try direct launch from the designated origin
3. if empty, try cross-hub fallback to another viable origin for the same destination
4. if no viable origin has inventory, queue at the original origin

This is a deliberate behavioral choice: the simulator prefers serving demand from another active hub over forcing all demand to wait for explicit rebalancing first.

### Queue drain behavior

When a drone completes cooldown and checks into its destination hub:

1. the drone returns to the destination hub's idle pool
2. the registry immediately drains any queued origin demand for that hub

That behavior is now explicitly covered by tests.

## Finite-Fleet State

`FleetPool` is the dispatchable inventory model. It tracks:

- idle drones by hub
- queued orders by hub
- exact total fleet size

The recent refactor removed duplicated allocation logic by moving the exact-integer proportional allocator into `simulation/allocation.py`, which is now shared by:

- `FleetPool.from_hub_sizing()`
- deterministic target-allocation logic in `simulation/rebalancing.py`

## Verified Behaviors

The dispatching layer now has focused regression coverage for:

- cross-hub fallback when the original origin hub is empty
- queued order drain after a drone checks back into a destination hub
- CLI and setup changes that feed the simulator without changing public entrypoints

## Still Open

- fallback routing is operationally convenient but still simplified; it does not model a customer-level reassignment penalty
- RL rebalancing moves drones in the pool directly rather than as visible dead-head flights
- upstream ground routing stubs still affect which corridors receive demand weight in the simulated network
