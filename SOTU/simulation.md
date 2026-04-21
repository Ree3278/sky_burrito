# State of the Union — Simulation
**Date:** April 21, 2026  
**Module:** `simulation/`  
**Depends on:** `corridor_pruning/` shortlist · `hub_sizing/` M/G/k sizing results · `models/` PPO weights

---

## What This Stage Does

Converts the static analysis — 20 pruned corridors, 9 active hubs — into a
**live digital twin** of the Friday night peak window (18:00–21:00). The simulation
runs on two layers:

1. **Physics layer** — Drones fly through a six-state machine, occupy landing pads, queue when the fleet is exhausted, and trigger craning events when destination pads are full.
2. **Intelligence layer** — A trained PPO agent observes fleet distribution and demand signals and issues rebalancing commands to prevent tidal flow imbalance from collapsing throughput on exporter hubs like Hub 3.

---

## Files

| File | Role |
|---|---|
| `config.py` | All tunable constants — time multiplier, colors, physics, fleet params |
| `clock.py` | `SimClock`: wall-clock → sim-time with configurable multiplier |
| `drone.py` | `Drone` agent + `DroneState` enum — six-state machine with Shapely position interpolation |
| `fleet.py` | `FleetPool` — finite fleet budget, per-hub checkout/checkin, order queue, dead-head reservation |
| `dispatcher.py` | Poisson order generator — emits `DispatchRequest` frozen dataclasses, carries over fractional arrivals |
| `registry.py` | Central loop — advances all drones, integrates FleetPool, drains queued orders after checkin, emits `SimSnapshot` |
| `rl_fleet_env.py` | Gymnasium `DroneFleetEnv` — 42D obs space, 9D action space, multi-objective reward shaping |
| `rl_training.py` | PPO training entry point — 4-phase curriculum, TensorBoard logging, checkpoint saving |
| `rl_inference.py` | Load trained weights, run evaluation episodes, report reward breakdown |
| `layers.py` | Pydeck layer builders — arc corridors, hub scatter, drone dots, craning rings, saturation overlays |
| `app.py` | Streamlit frontend — live map, sidebar controls, metrics, featured route card |

**Launch command:**
```bash
uv run streamlit run simulation/app.py
```

---

## What's Working

### Drone state machine (6 states)

```
IDLE → TAKEOFF → CRUISE → LANDING → COOLDOWN → IDLE
                               ↓ (pad full)
                            CRANING → (pad opens) → COOLDOWN
```

COOLDOWN_S = 330 s (manual kiosk spec). Position interpolates linearly along
the corridor LineString during CRUISE. Altitude tracked independently across
climb/cruise/descent phases.

### Finite fleet — `FleetPool`

The infinite-drone limitation is **resolved**. Every drone is now a physical
unit with a lifecycle:

```
Order arrives at Hub H
  ├─ idle drone available at H?  YES → checkout, dispatch
  └─ no drone available?         NO  → enqueue order, wait

Drone completes COOLDOWN at Hub H'
  ├─ checkin to H' idle pool
  └─ pending order queued at H'?  YES → re-dispatch immediately
```

Fleet is initialised via `FleetPool.from_hub_sizing()` — largest-remainder
allocation proportional to hub `match_score`. Default fleet: 30 drones.
Supported fleet sizes for the trained RL policy: **10, 20, 30, 40, 50 drones**.

### Dispatcher

`DispatchRequest` frozen dataclasses (not Drone objects) are emitted per order.
Poisson sampling from the weighted corridor list, with fractional leftover
carry-over between ticks for numerical accuracy.

### Streamlit app

- Pydeck map with `MAP_BEARING=-8°`, `MAP_PITCH=38°`, light basemap
- **ArcLayer** — 20 shortlisted corridors, arc width ∝ demand weight, great-circle interpolation, highlighted featured route
- **ScatterplotLayer** — hubs sized by k-pads, colored by tier, turns solid red when saturated
- **ScatterplotLayer** — live drone dots color-coded by state
- **ScatterplotLayer** — pulsing red ring on craning drones and saturated hub rings
- Sidebar controls — time multiplier (1×–120×), demand scale, automated swap toggle, Start/Pause/Reset
- Live metrics — sim time, active drones, craning count, orders dispatched, queue depth
- Per-hub utilisation bars with craning count and tier badge
- Featured route card (dark) with cost arbitrage and CO₂ savings
- CSS-styled sim-hero banner, sim-chip badges, sim-status-cards

---

## Tidal Flow — The Problem That Was Solved

Summing appearances across the top-20 corridors:

| Hub | As origin | As destination | Net flow |
|---|---|---|---|
| Hub 3  | 1 | 0 | −1 (pure exporter) |
| Hub 11 | 4 | 3 | −1 (exporter) |
| Hub 9  | 3 | 2 | −1 (exporter) |
| Hub 1  | 3 | 3 | 0 (balanced) |
| Hub 6  | 1 | 5 | **+4 (importer / drone sink)** |

Without rebalancing, Hub 3 runs dry while Hub 6 accumulates idle drones. The
finite fleet makes this tidal drift immediately visible — Hub 3 order queue grows,
Hub 6 idles. The RL policy's job is to issue dead-head commands before the
exporter hubs go dark.

---

## RL Policy — PPO Fleet Optimization

### Gymnasium Environment (`rl_fleet_env.py`)

**Observation space (42D):**
- 9 values: idle drones per hub (normalised)
- 9 values: queued orders per hub (normalised)
- 9 values: drones en-route to each hub (normalised)
- 9 values: demand rate per hub at current sim hour
- 6 values: global signals (time-of-day, fleet utilisation, fulfillment rate, craning rate, queue ratio, deadhead ratio)

**Action space (9D continuous):** One scalar per active hub. Positive value on hub H = move drones *to* H (rebalance). Negative = hold or source from H. Magnitude controls aggressiveness.

**Reward shaping (per step):**
| Signal | Value |
|---|---|
| Fulfilled order | +50 |
| Queued order (penalty) | −10 |
| Craning event (penalty) | −200 |
| Dead-head flight (overhead) | −5 |
| Idle drone at correct hub | +10 |

**Demand generator** — M/G/k Gaussian demand peaks at meal-times:
- Breakfast (07:00–09:00)
- Lunch (11:30–13:30)
- Snack (15:00–17:00)
- Dinner (18:00–20:00)

### Curriculum Learning (`rl_training.py`)

Four phases of increasing complexity:

| Phase | Scope | Episode | Timesteps | LR |
|---|---|---|---|---|
| 1 | Single hub (Hub 6) | 6 h | 50k | 1e-3 |
| 2 | Two hubs bidirectional (Hub 11 ↔ Hub 9) | 12 h | 100k | 5e-4 |
| 3 | Full network (9 hubs, 20 routes) | 24 h | 500k | 3e-4 |
| 4 | Full network + meal-time peaks | 24 h | 1M | 2e-4 |

**Architecture:** PPO + MlpPolicy, γ=0.99, GAE λ=0.95, clip=0.2, ent_coef=0.01, n_epochs=20.
Device auto-detection: CUDA → MPS → CPU.

### Trained Weights — Current State (`models/`)

Training has been run through **Phase 3** across 5 fleet sizes:

| Fleet size | Phases trained | Checkpoints | Final model |
|---|---|---|---|
| 10 drones | Phase 3 only | 50k–500k (10 checkpoints) | `fleet_10/ppo_fleet_10_phase_3.zip` |
| 20 drones | Phase 1 → 2 → 3 (full curriculum) | Phase 1: 5k–50k · Phase 2: 10k–100k · Phase 3: 50k–500k | `fleet_20/ppo_fleet_20_phase_3.zip` |
| 30 drones | Phase 3 only | 50k–500k | `fleet_30/ppo_fleet_30_phase_3.zip` |
| 40 drones | Phase 3 only | 50k–500k | `fleet_40/ppo_fleet_40_phase_3.zip` |
| 50 drones | Phase 3 only | 50k–500k | `fleet_50/ppo_fleet_50_phase_3.zip` |

Fleet 20 is the **reference model** — the only fleet size that ran the full
3-phase curriculum. Fleets 10/30/40/50 were trained at phase 3 directly and
can be compared to the fleet-20 baseline to study the effect of fleet size on
agent performance.

Phase 4 (full network + meal-time demand peaks, 1M steps) has **not yet been run**
for any fleet size. The `rl_training.py` scaffold is ready.

### Inference (`rl_inference.py`)

```bash
python simulation/rl_inference.py --fleet-size 20 --phase 3
```

Reports: `avg_reward`, `avg_fulfillment`, `std_reward`, and per-component reward
breakdown across N evaluation episodes.

---

## Smoke Test Results (Original Phase — now superseded)

Before the finite fleet and RL were added, the original smoke test showed:

```
Sim time:          18:14
Active drones:     38
Orders dispatched: 59
Craning events:    1  ← Hub 1 hit 9/8 pads at 18:09
```

This result validated the craning model. The infinite-drone architecture has
since been replaced — the smoke test figures are not directly comparable to the
current simulation which respects fleet budget and queues orders.

---

## Open Items

| Priority | Task | Notes |
|---|---|---|
| **1** | Wire trained model into `app.py` live dispatch loop | `rl_inference.py` exists; `app.py` needs `--use-rl` branch |
| **2** | Phase 4 training (meal-time peaks, 1M steps) | Scaffold ready in `rl_training.py` |
| **3** | A/B panel in Streamlit: RL policy vs. no-rebalancing | Show Hub 3 queue collapse without RL |
| **4** | Real OSMnx ground times | `TRAFFIC_MULTIPLIER=1.0` stub still active in `ground_model.py` |
| **5** | Wire building obstacles into corridor altitude | `obstacles.py` exists but `add_obstacles_to_corridors()` not called in pipeline |

---

## Roadmap Summary

| Component | Status |
|---|---|
| Drone state machine (6 states) | ✅ Complete |
| Poisson dispatcher + order queueing | ✅ Complete |
| Finite fleet budget (FleetPool) | ✅ Complete |
| Tidal flow detection | ✅ Complete (visible in hub queue depth) |
| Pydeck + Streamlit live map | ✅ Complete |
| Gymnasium RL environment (42D/9D) | ✅ Complete |
| PPO curriculum training (Phases 1–3) | ✅ Complete — weights in `models/` |
| RL model inference evaluation | ✅ Complete (`rl_inference.py`) |
| Live RL policy in Streamlit sim | ⏳ Pending — next integration milestone |
| Phase 4 training (meal-time peaks) | ⏳ Optional — scaffold ready |
