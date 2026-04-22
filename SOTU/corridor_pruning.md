# State of the Union — Corridor Pruning
**Date:** April 22, 2026  
**Module:** `corridor_pruning/`

## What This Layer Does

Corridor pruning scores directed hub-to-hub routes and returns the highest-value corridors for sizing and simulation. The current scoring pipeline combines:

- drone flight time and energy
- ground delivery time and cost
- per-corridor demand weight
- CO2 savings

The shortlist remains the source of truth for both hub sizing and the live simulation setup.

## What Is Real Today

### Wired in

- 12 fixed hubs and all directed corridor candidates
- physics-based drone cost model
- Uber-style ground payout model
- CO2 scoring
- building obstacle loading when `buildings_csv` is provided

The pruning stage now does call into `obstacles.py` when the building CSV is available, so obstacle heights are no longer just a documentation placeholder.

### Still stubbed

- road routing and traffic in `ground_model.py`
- any corridor that depends on real OSMnx travel times still reports `used_stubs=True`

So the corridor list is useful and internally consistent, but it is not yet a full street-network-accurate benchmark.

## Current Scoring Shape

`ScoredCorridor` carries the full runtime payload used downstream:

- origin/destination corridor object
- drone and ground times
- energy ratio
- cost arbitrage
- CO2 reduction
- composite score
- stub usage flag

That object is serialized into the persisted simulation setup and reconstructed later by the runtime environment builders.

## Refactor Notes

The recent refactor did not redesign pruning math. It did make the downstream contracts clearer:

- setup serialization now stores route-level fields explicitly
- runtime reconstruction no longer depends on implicit corridor mutation only
- the docs no longer claim obstacle wiring is still pending when CSV-backed obstacle loading is already implemented

## Main Open Item

The next meaningful improvement is still the same one:

- replace the stub ground model with real OSMnx-based routing and travel times

Until that happens, corridor ranking remains strongest on relative drone-side economics and weaker on real ground-side travel fidelity.
