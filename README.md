# 🌯 Sky Burrito — SF Inter-District Drone Delivery Network

> **Status:** Transitioning from Spatial Siting → Dynamic Network Modeling (April 2026)

A data-driven proof-of-concept for a hub-to-hub aerial logistics network in San Francisco's Mission–Noe Valley corridor. The core thesis: drones beat ground couriers in a city shaped by steep grades and chronic gridlock — but only on the *right* routes, for the *right* orders, at the *right* time.

---

## The Problem

San Francisco's street grid was not designed for speed. Steep topography forces cars onto circuitous routes; a 1.2-mile straight-line trip across Dolores Park can translate to a 2.4-mile drive with turns, stoplights, and hills. The resulting "Topographical Arbitrage" — the gap between as-the-crow-flies distance and actual driving distance — is the economic foundation of this project.

Sky Burrito doesn't aim to replace every delivery. It targets the high-value corridors where that arbitrage is large enough to justify the infrastructure.

---

## Geographic Scope

All analysis is locked to a single bounding box in central San Francisco:

| Boundary | Location |
|---|---|
| **West** | Twin Peaks / Noe Valley edge |
| **East** | Potrero Hill / Mission edge |
| **North** | ~Market St / Van Ness Ave |
| **South** | Cesar Chavez St |

```
MIN_LON = -122.4450   MAX_LON = -122.4080
MIN_LAT =  37.7480    MAX_LAT =  37.7680
```

---

## Architecture: The Hub-to-Kiosk Model

The network follows a **kiosk-to-kiosk** delivery model — no backyard landings, no rooftop-to-doorstep handoffs. Every flight begins and ends at a secured public kiosk within a 5-minute walk (~420 m) of the end user.

```
[Restaurant] → [Launch Hub] ──(drone)──▶ [Drop Kiosk] → [Customer walks ≤5 min]
```

Twelve candidate Launch Hubs are sited using a **bimodal K-Means strategy**:
- **Source Hubs** cluster around high restaurant density (e.g., Hubs 5 and 12)
- **Sink Hubs** cluster around high residential unit counts (e.g., Hubs 6 and 10)

---

## Data Sources

Three public City of San Francisco datasets power the spatial analysis:

### 1. Registered Business Locations (`Registered_Business_Locations_-_San_Francisco_20260410.csv`)
Active food-service businesses (NAICS code `722*`) within the bounding box. Filtered to exclude any with a `Business End Date`, `Location End Date`, or `Administratively Closed` flag.

**Result:** 927 active restaurant-class businesses → candidate supply points for Launch Hubs.

### 2. Building Footprints (`Building_Footprints_20260410.csv`)
3D polygon footprints of every structure over 2 meters tall, with `hgt_median_m`. Used to compute the per-route **Climb Cost**: the minimum cruising altitude a drone must reach to safely clear all obstacles on a given flight path.

**Result:** 15,559 building obstacles mapped in the corridor.

### 3. SF Land Use — 2023 (`San_Francisco_Land_Use_-_2023_20260410.csv`)
Residential parcel centroids with `resunits` counts. Used to score potential Kiosk sites by "Residential Gravity" — the number of dwelling units within a 420-meter walk zone.

**Result:** 13,043 residential properties tracked as demand sinks.

---

## Notebooks

### `group_project.ipynb` — Core Data Pipeline

The foundational preprocessing notebook. Runs in order:

1. **Bounding box definition** — establishes the corridor in lat/lon
2. **Restaurant ingestion** — loads, filters, and converts the business registry to a GeoDataFrame
3. **Building obstacle ingestion** — loads footprints, filters by height threshold, exports `mission_noe_buildings.geojson`
4. **Residential sink ingestion** — loads land use, converts polygons to centroids, exports `mission_noe_residential_sinks.geojson`
5. **OSMnx street graph** — downloads the drivable road network for the corridor to serve as the ground-transit benchmark in arbitrage calculations

### `group_project_visuilzation.ipynb` — Spatial Analysis & Hub Optimization

Builds on the core pipeline and adds:

- **Density maps** — separate and overlaid restaurant vs. residential heatmaps
- **Building height distribution** — informs minimum drone cruising altitude
- **5-minute walk zone analysis** — 420 m radius buffers around candidate kiosk sites, scored by `resunits` coverage
- **K-Means cluster sweep** — tests `k = {4, 5, 6, 7, 8, 10, 12}` hub counts to find the coverage/cost sweet spot
- **Launch pad optimization report** — prints a full infrastructure summary with per-hub coverage metrics

---

## Key Mathematical Frameworks

### Topographical Arbitrage (Route Pruning)
Only routes where `Δt(drone) − Δt(car)` exceeds a threshold are kept. The OSMnx graph provides realistic car travel times; drone time is straight-line distance at cruise speed. Of the 144 possible hub-to-hub pairings (12 × 12), the target is to prune to ~20 high-value corridors.

### Climb Cost (Energy Modeling)
Battery drain is modeled as a function of horizontal distance plus vertical lift:

```
E_total = E_horizontal + E_climb
E_climb = m × g × h_obstacle_clearance
```

The building footprints dataset supplies `h_obstacle_clearance` per route. This lets the model compare drone energy cost against the fuel/time waste of a car idling in traffic.

### M/G/k Queuing (Infrastructure Sizing)
Demand is simulated using a **Non-Homogeneous Poisson Process** to model Friday-night order volume surges. The M/G/k queuing model then solves for `k` (landing pads + battery bays per hub) to prevent "craning" — drones idling in the air waiting for a pad to open.

---

## Setup

```bash
pip install pandas geopandas shapely scikit-learn osmnx matplotlib
```

You will also need the three raw CSV data files in the project root (not committed to the repo due to size):
- `Registered_Business_Locations_-_San_Francisco_20260410.csv`
- `Building_Footprints_20260410.csv`
- `San_Francisco_Land_Use_-_2023_20260410.csv`

Run `group_project.ipynb` first to generate the GeoJSON intermediates, then `group_project_visuilzation.ipynb` for analysis and hub optimization.

---

## Roadmap

| Priority | Task | Objective |
|---|---|---|
| **CRITICAL** | Corridor Pruning | Filter 144 possible routes → top ~20 by traffic arbitrage |
| **HIGH** | Energy Analysis | Calculate exact Climb Cost penalty per route |
| **MEDIUM** | M/G/k Sizing | Assign pad/bay counts to each of the 12 hubs |
| **LOW** | Regulatory Prep | Cross-reference hub sites with 2026 FAA BVLOS corridors |

**Phase 2 (acknowledged, not yet modeled):** Tidal flow rebalancing — managing the directional imbalance between lunch/dinner rush outbound flights and the need to reposition drones for the next surge. Currently treated as a fixed operational overhead multiplier (`1.X`).

---

## Project Status

The spatial foundation is complete. 12 hub locations are mathematically defensible. The next phase is turning the static map into a dynamic simulation: generating realistic order volumes, routing them through the pruned corridor graph, and measuring throughput against the M/G/k infrastructure budget.
