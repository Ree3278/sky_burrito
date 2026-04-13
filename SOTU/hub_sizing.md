# State of the Union — Hub Sizing (M/G/k)
**Date:** April 12, 2026
**Module:** `hub_sizing/`
**Depends on:** `corridor_pruning/` shortlist (20 routes, 10 active hubs)

---

## What This Stage Does

Takes the pruned corridor shortlist and answers one question per hub: **how many landing pads and battery bays do you need to keep drones from craning (circling in the air waiting for a pad) during the Friday night peak?**

The tool is the **M/G/k queuing model**, where M = Poisson arrivals, G = general service time, k = number of pads. The solver finds the minimum k such that P(craning) ≤ 5% and pad utilisation ≤ 85%.

---

## Files Built

| File | Role |
|---|---|
| `demand.py` | Stub NHPP → peak arrival rate λ per hub |
| `service.py` | Stub service time distribution: E[S], c_s² |
| `mgk.py` | Erlang-C core + Whitt M/G/k approximation + k solver |
| `sizing.py` | Applies M/G/k to all 10 active hubs, prints report |

---

## Current Results (Both Scenarios)

### Manual Kiosk — E[S] = 330 s (5.5 min), c_s² = 1.0

| Hub | λ/hr | Load (E) | Pads | Util% | P(cran)% | P(cran) @k-1 | Tier |
|---|---|---|---|---|---|---|---|
| Hub 1 | 36.4 | 3.34 | **8** | 41.7% | 2.3% | 6.2% | 🔴 HEAVY |
| Hub 11 | 35.2 | 3.23 | **8** | 40.4% | 1.9% | 5.3% | 🔴 HEAVY |
| Hub 2 | 30.0 | 2.75 | **7** | 39.2% | 2.5% | 7.0% | 🔴 HEAVY |
| Hub 6 | 25.1 | 2.30 | **6** | 38.3% | 3.3% | 9.8% | 🔴 HEAVY |
| Hub 7 | 21.9 | 2.01 | **6** | 33.5% | 1.8% | 6.1% | 🔴 HEAVY |
| Hub 9 | 19.3 | 1.77 | **5** | 35.4% | 3.8% | 12.2% | 🟡 MODERATE |
| Hub 10 | 13.3 | 1.22 | **4** | 30.6% | 3.9% | 14.8% | 🟡 MODERATE |
| Hub 5 | 10.8 | 0.99 | **4** | 24.8% | 2.0% | 9.0% | 🟢 LIGHT |
| Hub 3 | 4.6 | 0.42 | **3** | 14.2% | 1.0% | 7.4% | 🟢 LIGHT |
| Hub 4 | 3.3 | 0.30 | **2** | 14.9% | 3.9% | 29.8% | 🟢 LIGHT |
| **TOTAL** | | | **53 pads + 53 bays** | | | | |

### Automated Battery Swap — E[S] = 210 s (3.5 min), c_s² = 0.25

| Hub | λ/hr | Load (E) | Pads | Util% | P(cran)% | P(cran) @k-1 | Tier |
|---|---|---|---|---|---|---|---|
| Hub 1 | 36.4 | 2.12 | **5** | 42.5% | 4.6% | 12.9% | 🔴 HEAVY |
| Hub 11 | 35.2 | 2.06 | **5** | 41.1% | 4.1% | 11.7% | 🔴 HEAVY |
| Hub 2 | 30.0 | 1.75 | **5** | 34.9% | 2.3% | 7.4% | 🟡 MODERATE |
| Hub 6 | 25.1 | 1.46 | **4** | 36.6% | 4.3% | 14.0% | 🟡 MODERATE |
| Hub 7 | 21.9 | 1.28 | **4** | 32.0% | 2.8% | 10.2% | 🟡 MODERATE |
| Hub 9 | 19.3 | 1.13 | **4** | 28.2% | 1.9% | 7.6% | 🟡 MODERATE |
| Hub 10 | 13.3 | 0.78 | **3** | 25.9% | 3.0% | 13.6% | 🟢 LIGHT |
| Hub 5 | 10.8 | 0.63 | **3** | 21.1% | 1.8% | 9.5% | 🟢 LIGHT |
| Hub 3 | 4.6 | 0.27 | **2** | 13.5% | 2.0% | 16.9% | 🟢 LIGHT |
| Hub 4 | 3.3 | 0.19 | **2** | 9.5% | 1.0% | 11.9% | 🟢 LIGHT |
| **TOTAL** | | | **37 pads + 37 bays** | | | | |

**Automating the battery swap saves 16 pads (30%) across the network.** That decision should be resolved before any site construction begins.

---

## Key Findings

**Hub 11 and Hub 1 are the network's load-bearing nodes.** They each appear in 7 and 6 shortlist corridors respectively and carry the highest arrival rates. They need 8 pads each in the manual scenario — the most of any hub — and are the last to drop to MODERATE tier even with automation.

**The `@k-1` column is the sharpest signal in the report.** It shows craning probability if one pad is offline (maintenance, weather, malfunction). Hub 4's `@k-1` jumps from 3.9% → 29.8% — that second pad is not insurance, it's structural. By contrast, Hub 1's 8th pad only moves the needle from 2.3% → 6.2%, which is a softer dependency.

**All utilisation figures are low (10–42%).** This is a deliberate consequence of targeting P(cran) ≤ 5%. The pads are sized for the peak surge, not average throughput. During off-peak hours, most pads will be idle. This is the correct trade-off for a kiosk-to-kiosk model where craning drones are a visible operational failure.

**Hubs 8 and 12 require zero infrastructure investment at this stage.** They produced no shortlist corridors. Either their traffic is absorbed by adjacent hubs or their arbitrage score didn't clear the filter. They remain candidate sites for Phase 2 rebalancing.

---

## What's Stubbed

### 1. Demand model — `demand.py` [HIGH IMPACT]
The arrival rate λ per hub is derived by distributing a flat 200 orders/hr across hubs proportional to their corridor flow weight. This is a stand-in for a Non-Homogeneous Poisson Process fit to real order data.

The absolute pad counts (53 vs 37) will shift with real λ. The relative ranking of hubs — which are HEAVY vs LIGHT — is more stable and likely survives a real demand model.

**To replace:** Run NHPP simulation on historical Friday-night order volumes (POS data, delivery platform export). Feed per-hub λ(t) into `solve_k()` at the peak 15-minute bucket.

### 2. Service time — `service.py` [HIGH IMPACT]
E[S] = 330 s (manual) and 210 s (automated) are estimates based on analogous drone dock systems. Neither has been measured on actual hardware.

The coefficient of variation c_s² = 1.0 (manual) and 0.25 (automated) are also assumptions. In practice, a manual swap will have high variance (operator speed, package complexity, weather) and a well-tuned robot will be tighter.

**To replace:** Time a prototype battery swap cycle under realistic conditions. Even 20 repetitions would give a defensible mean and variance.

### 3. Demand distribution method [MEDIUM IMPACT]
The current method counts corridor appearances weighted by `demand_weight` (restaurants × resunits) and normalises. This assumes every corridor generates equal orders per unit of demand weight, which is unlikely — popular restaurant clusters send more orders than the raw match score implies.

**To replace:** Use the NHPP simulation output directly once available.

---

## Immediate Next Steps

The sizing module is complete as a skeleton. There are no further structural pieces to add before real data arrives. The two stubs above are the only blockers to production-grade numbers.

The next modeling stage is the **simulation layer** — running the Non-Homogeneous Poisson Process to generate realistic per-hub order volumes for a Friday evening window, which will simultaneously unblock both the demand stub here and the traffic multiplier stub in `corridor_pruning/ground_model.py`.
