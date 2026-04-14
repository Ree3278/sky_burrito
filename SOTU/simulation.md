# State of the Union — Simulation
**Date:** April 13, 2026
**Module:** `simulation/`
**Depends on:** `corridor_pruning/` shortlist · `hub_sizing/` M/G/k sizing results

---

## What This Stage Does

Converts the static analysis — 20 pruned corridors, 10 sized hubs — into a
**live digital twin** of the Friday night peak window (18:00–21:00). Drones
are spawned by a Poisson dispatcher, fly through a five-state machine, occupy
landing pads, and surface craning events in real time on a Pydeck map hosted
by Streamlit.

The goal is to move from a defensible spreadsheet to a convincing visual
business case: watch Hub 1 go red at 18:14 because all 8 pads are full.

---

## Files Built

| File | Role |
|---|---|
| `config.py` | All tunable constants — time multiplier, colors, physics, fleet params |
| `clock.py` | `SimClock`: wall-clock → sim-time with configurable multiplier |
| `drone.py` | `Drone` agent + `DroneState` enum — five-state machine with Shapely position interpolation |
| `dispatcher.py` | Poisson order generator — samples corridors by demand weight, spawns `Drone` objects |
| `registry.py` | Central loop — advances all drones, tracks pad occupancy, detects craning, emits `SimSnapshot` |
| `layers.py` | Pydeck layer builders — arc corridors, hub scatter, drone dots, craning rings |
| `app.py` | Streamlit frontend — map + live metrics, sidebar controls |

**Launch command:**
```bash
uv run streamlit run simulation/app.py
```

---

## What's Working

### Drone state machine
Five states are fully implemented and transition correctly:

```
TAKEOFF → CRUISE → LANDING → COOLDOWN → (deleted)
                      ↓ (pad full)
                   CRANING → COOLDOWN (when pad opens)
```

Position interpolates linearly along the corridor `LineString` during CRUISE.
Altitude is tracked independently (climb / cruise / descent phases).

### Dispatcher
Poisson sampling from a weighted corridor list. Each tick generates `Poisson(λ × dt)` orders, each assigned to a corridor proportional to `demand_weight`. Fractional arrivals carry over between ticks for numerical accuracy.

### Registry
Pad occupancy is recounted from live drone states every tick — no counters to
drift out of sync. Craning events are detected on the transition into the
`CRANING` state and logged to a running total.

### Streamlit app
- **Pydeck dark map** centered on Mission–Noe with pitch=45° tilt
- **ArcLayer** — 20 shortlisted corridors (static, always visible)
- **ScatterplotLayer** — hubs, sized by k-pads, colored by tier (red=heavy, amber=moderate, green=light), turns solid red when saturated
- **ScatterplotLayer** — live drone dots, color-coded by state
- **ScatterplotLayer** — pulsing red ring on every craning drone
- **Sidebar controls** — time multiplier (1×–120×), demand scale (0.5×–3×), automated swap toggle, pad count override, Start/Pause/Reset
- **Live metrics row** — sim time, active drones, craning count, orders dispatched
- **Per-hub utilisation bar** — pads_in_use / k_pads with craning count

### Smoke test result (15 sim-minutes)
```
Sim time:          18:14
Active drones:     38
Orders dispatched: 59
Craning events:    1           ← Hub 1 hit 9 drones against 8 pads at 18:09
```

Hub utilisation after 15 sim-min (manual kiosk spec, demand=200/hr):
```
Hub  1  [█████████░]  9/8   ← already saturated once
Hub 11  [█████░░░  ]  5/8
Hub  6  [████░░    ]  4/6
Hub  7  [███░░░    ]  3/6
Hub  2  [█░░░░░░   ]  1/7
Hub  9  [█░░░░     ]  1/5
```

The pad contention model is behaving correctly. Hub 1 is the first to crack,
exactly as the M/G/k model predicted it would be the most load-bearing node.

---

## Key Limitation — Infinite Drone Fleet

**This is the most significant gap in the current simulation.**

Every order spawns a brand-new `Drone` object from nothing. After COOLDOWN
completes, the drone is deleted from the registry and never seen again.
There is no fleet budget, no recycling, no repositioning.

### What this breaks

The **pad occupancy model is correct** — pads fill, craning fires, the
utilisation numbers are meaningful. But the **supply side is unconstrained**.
In reality you have a fixed fleet of physical drones (e.g., 30 units) distributed
across 10 hubs. Once all are in the air or on pads, new orders queue at
the *origin hub* — not just at the destination pad. This queuing pressure
doesn't exist in the current model.

### The tidal flow consequence

The shortlist is directional. Summing appearances across the top-20 corridors:

| Hub | As origin | As destination | Net flow |
|---|---|---|---|
| Hub 11 | 4 | 3 | −1 (exporter) |
| Hub 1 | 3 | 3 | 0 (balanced) |
| Hub 6 | 1 | 5 | **+4 (importer)** |
| Hub 9 | 3 | 2 | −1 (exporter) |
| Hub 3 | 1 | 0 | −1 (pure exporter) |

Hub 6 is a drone sink — it receives far more flights than it dispatches.
Hub 3 is a pure exporter. Run the simulation long enough and Hub 3 runs dry
while Hub 6 overflows with idle drones. The project brief calls this "Tidal
Flow" and flags it as a Phase 2 concern. With infinite drones it never
surfaces.

---

## What's Planned Next — Tidal Flow + Fleet Budget

Two interlocking additions are designed and ready to implement:

### 1. Fleet budget + drone recycling

Replace the spawn-and-delete lifecycle with a physical fleet:

```
Order arrives at Hub H
  └─ idle drone available at H?
       YES → checkout drone, dispatch on corridor
       NO  → enqueue order, wait
       
Drone completes COOLDOWN at Hub H'
  └─ checkin drone to H' idle pool
  └─ pending order in H' queue?
       YES → immediately re-dispatch
       NO  → drone sits idle at H'
```

New file: **`simulation/fleet.py`** — `FleetPool` managing a per-hub integer
count of idle drones. Total across all hubs = `FLEET_SIZE` (constant, e.g. 30).
Initial distribution: proportional to hub `match_score`.

### 2. Dead-head rebalancing — `TidalFlowPolicy` (SPU)

A pluggable **Strategic Policy Unit** triggered when tidal imbalance crosses
a threshold. The default policy is threshold-based greedy nearest-surplus:

```
Every REBALANCE_INTERVAL_S sim-seconds:
  For each hub H where idle_count < LOW_WATER_MARK:
    Find hub H' = nearest hub where idle_count > HIGH_WATER_MARK
    Dispatch a DEAD_HEAD drone: H' → H
    (no payload, shorter cooldown — battery swap only, ~180s)
```

New file: **`simulation/rebalancing.py`** — abstract `RebalancingPolicy` base
class + `TidalFlowPolicy` implementation + `NoRebalancing` null policy for
A/B comparison.

The `DEAD_HEAD` state slots cleanly into the existing state machine:
```
DEAD_HEAD_TAKEOFF → DEAD_HEAD_CRUISE → DEAD_HEAD_LANDING → COOLDOWN(180s) → IDLE
```

Drones in DEAD_HEAD are rendered as dim grey dots on the map — visible but
clearly distinguished from payload flights. Their total count and cost
(distance flown × energy) is tracked as the `1.X` overhead multiplier.

### The "mic-drop" experiment this enables

With fleet budget + tidal flow implemented:

1. Set `FLEET_SIZE = 20`, `pad_override = 2` (under-built hubs)
2. Turn off rebalancing (`NoRebalancing` policy)
3. Watch Hub 3 go dark (no drones to dispatch) while Hub 6 queues up idle drones
4. Turn on `TidalFlowPolicy`
5. Watch dead-head grey dots redistribute the fleet and Hub 3 come back online

That sequence — broken network → rebalancing kicks in → recovery — is the
business case for the operational overhead budget.

---

## Immediate Next Steps

| Priority | Task | File |
|---|---|---|
| **1** | `FleetPool` class + initial distribution | `simulation/fleet.py` (new) |
| **2** | Drone lifecycle: checkin/checkout + order queue | `simulation/drone.py`, `simulation/dispatcher.py` |
| **3** | `DEAD_HEAD` state in drone state machine | `simulation/drone.py` |
| **4** | `TidalFlowPolicy` SPU | `simulation/rebalancing.py` (new) |
| **5** | Wire fleet + rebalancing into registry tick loop | `simulation/registry.py` |
| **6** | Add fleet metrics + dead-head layer to app | `simulation/app.py`, `simulation/layers.py` |
