# Sky Burrito Final Summary Report

Date: April 21, 2026
Repo: `sky_burrito`

## 1. Executive Summary

Sky Burrito is a San Francisco drone-delivery prototype focused on a narrow but defensible claim: drones are only worth building into the delivery stack on corridors where street geometry, hills, signals, and congestion make ground travel meaningfully worse than straight-line flight.

The current codebase is no longer just exploratory notebook work. It is now a modular Python project with a clear modeling chain:

1. `data_processing/` prepares the geospatial inputs.
2. `siting_strategy/` sites candidate hubs and scores 5-minute walk access.
3. `corridor_pruning/` scores all hub-to-hub corridors and keeps the best ones.
4. `hub_sizing/` sizes landing pads and battery bays with M/G/k queueing.
5. `simulation/` runs a live prototype showing dispatches, drone states, pad usage, and craning.

The biggest recent operational takeaway is that the simulation path is now concrete enough to treat dispatching as a real modeled stage rather than a placeholder idea. The dispatcher is still a stub NHPP, but its rules are clear, reproducible, and already wired into the live app.

## 1A. Story-Based Summary For Slides Or Presentation

If we had to explain the project without starting from code, the story is simple: we are not trying to prove that drones can deliver food everywhere. We are trying to identify the small set of situations where drones make operational sense and then design a network around those situations.

Our core heuristic is that drones are only valuable when they solve a real urban friction problem. In a dense city like San Francisco, ground delivery is slowed down by road geometry, intersections, hills, and congestion, while drones can travel much closer to a straight line. So the project begins by asking a business question, not an aviation question: where does the city create enough friction on the ground that an aerial shortcut becomes worth it?

From there, the project follows a sequence of practical filters. First, we look for places with restaurant activity, because hubs only matter if they are near supply. Second, we look for nearby residential demand within a reasonable walking distance, because the system is designed around a hub-to-kiosk model rather than door-to-door drone dropoff. Third, we test which hub-to-hub corridors save enough time over ground travel to justify flying at all. Fourth, we ask whether those promising corridors carry enough demand to matter commercially. Finally, we size the hubs so that the network can actually absorb peak demand without creating excessive waiting in the air.

That means the project is really built on a chain of heuristics:

- Put hubs near clusters of restaurants.
- Prefer hubs that also cover dense residential areas within a 5-minute walk.
- Keep only corridors where drones produce meaningful time savings.
- Penalize corridors that consume too much energy relative to the benefit.
- Prioritize corridors where origin supply and destination demand are both strong.
- Size hub infrastructure around reliability, especially avoiding too much craning during peaks.

So the value of Sky Burrito is not just that it simulates drones. The value is that it gives us a decision framework. It helps answer: where should we place hubs, which links are worth operating, and how much infrastructure do we need before the system breaks under real demand?

For an audience, the takeaway is that this is a selective network design problem. We are deliberately narrowing from "all possible drone routes" to "the few routes that are fast enough, useful enough, and reliable enough to justify operation." That is the role of the heuristics in this project: not to make the model simplistic, but to make the concept operational.

## 2. What Was Verified

This report was built from the current source code and a local smoke run of the runnable analytical path.

Verified with `./.venv/bin/python`:

- `corridor_pruning.prune_corridors()` runs successfully.
- `hub_sizing.size_hubs()` runs successfully on the current shortlist.
- `simulation.app` and `simulation.rebalancing` import successfully.

Notes:

- `uv` is referenced in docs, but `uv` is not installed in this shell.
- Importing `simulation.app` outside `streamlit run` produces expected Streamlit warnings, but the module imports successfully.
- The full raw-data siting pipeline was not rerun because the large SF CSV inputs are not present in this checkout.

## 3. End-to-End Project Flow

The intended project flow is:

`Raw city data -> cleaned geospatial layers -> hub siting -> corridor shortlist -> hub infrastructure sizing -> live dispatch simulation`

Operationally, the modeled delivery chain is:

`Restaurant -> Launch Hub -> Drone Corridor -> Drop Hub/Kiosk -> Customer Walk`

This repo is really solving three linked questions:

1. Where should hubs go?
2. Which hub-to-hub corridors are worth operating?
3. How much infrastructure is needed so the network does not fail under peak demand?

## 4. Module-by-Module Summary

### `data_processing/`

Purpose: turn public SF datasets into reusable spatial inputs inside one fixed Mission-Noe bounding box.

Key steps:

- `restaurants.py`
  - loads the registered business CSV
  - filters to active businesses only
  - keeps NAICS `722*` food-service records
  - converts WKT points to geometry
  - clips to the project bounding box

- `buildings.py`
  - loads building footprints
  - removes null geometry and null heights
  - keeps obstacles above 2 m
  - converts WKT polygons to geometry
  - clips to the bounding box
  - writes `mission_noe_buildings.geojson`

- `residential.py`
  - loads land use polygons
  - keeps parcels with `resunits > 0`
  - converts polygons to centroids in metric CRS for accuracy
  - clips to the bounding box
  - writes `mission_noe_residential_sinks.geojson`

- `street_network.py`
  - downloads the drivable OSMnx graph for the corridor
  - this graph is meant to become the real ground-travel benchmark

### `siting_strategy/`

Purpose: place candidate hubs and score their local usefulness.

Key algorithms:

- `clustering.py`
  - fits K-Means on restaurant coordinates
  - cluster centers become hub candidates
  - current default is 12 hubs

- `walk_zones.py`
  - uses a 5-minute walk radius
  - walk distance is computed as `1.4 m/s * 5 min = 420 m`
  - sums residential units inside each hub's walk zone

- `optimization.py`
  - sweeps `k in {4, 5, 6, 7, 8, 10, 12}`
  - measures total residential-unit coverage
  - recommends the smallest `k` that reaches the 50% coverage target

### `corridor_pruning/`

Purpose: reduce the full directed hub graph to a commercially useful shortlist.

Current implemented logic:

- `hubs.py`
  - stores the 12 canonical hubs as hard-coded outputs from prior siting work

- `corridors.py`
  - generates all directed hub pairs without self-loops
  - 12 hubs produce `12 * 11 = 132` directed corridors
  - computes straight-line distance with the Haversine formula
  - computes bearing for future directional analysis
  - defines corridor demand as:

`demand_weight = origin.restaurants_nearby * destination.resunits_nearby`

- `drone_model.py`
  - estimates flight time and energy with climb, cruise, and descent phases
  - current formulas:

`t_total = t_climb + t_cruise + t_descend`

`E_climb = (m * g * h) / (eta * 3600)`

`E_cruise = P_cruise * t_cruise / 3600`

  - if obstacle height is missing, it falls back to `120 m` cruise altitude

- `ground_model.py`
  - currently uses a stub ground model
  - road distance is estimated as:

`road_distance = straight_line_distance * 1.55`

  - total time is based on:
    - base speed `8.3 m/s`
    - `4 intersections/km`
    - `12 s` delay per intersection
    - traffic multiplier currently fixed at `1.0`

- `pruning.py`
  - scores every corridor
  - keeps only corridors satisfying all three filters:

`time_delta_s >= 120`

`energy_ratio > 1.0`

`demand_weight >= 100000`

  - ranks survivors by composite score:

`score = time_delta_s * log1p(demand_weight) * energy_ratio`

### `hub_sizing/`

Purpose: convert corridor activity into per-hub infrastructure requirements.

Key algorithms:

- `demand.py`
  - uses a stub peak demand of `200 orders/hour`
  - distributes that demand across active hubs proportional to corridor flow weight
  - each shortlisted corridor contributes its weight to both origin and destination hubs

- `service.py`
  - models pad service time as:

`approach + unload + battery_swap + load_next`

  - default manual kiosk mean service time:

`30 + 60 + 180 + 60 = 330 s`

  - automated swap scenario:

`30 + 60 + 60 + 60 = 210 s`

- `mgk.py`
  - solves pad count with M/G/k queueing
  - offered load:

`a = lambda * E[S]`

  - utilisation:

`rho = a / k`

  - craning probability uses Erlang-C plus Whitt's approximation:

`P_cran ≈ ErlangC(k, a) * (1 + c_s^2) / 2`

  - solver finds minimum `k` such that:

`P_cran <= 5%`

`utilisation <= 85%`

- `sizing.py`
  - sizes every active hub in the shortlist
  - sets battery bays equal to pad count
  - classifies hubs as `LIGHT`, `MODERATE`, or `HEAVY`

### `simulation/`

Purpose: simulate live traffic on the shortlisted network.

Key modules:

- `app.py`
  - Streamlit front end
  - loads corridor shortlist
  - sizes hubs
  - builds dispatcher and registry
  - renders hubs, corridors, drones, and craning events on a Pydeck map

- `clock.py`
  - controls simulated time
  - default start is Friday `18:00`
  - default duration is a 3-hour peak window

- `drone.py`
  - models each drone as a finite state machine
  - states:
    - `TAKEOFF`
    - `CRUISE`
    - `LANDING`
    - `COOLDOWN`
    - `CRANING`
    - `IDLE`

- `registry.py`
  - stores all active drones
  - counts pad occupancy by hub
  - detects craning events
  - retires drones after cooldown

- `rebalancing.py`
  - contains a separate idle-inventory rebalancing policy
  - currently present as an extension, but not wired into the main simulation loop

## 5. Current Dispatching Rules

This is the current operative dispatch logic in `simulation/dispatcher.py`.

### Demand generation

- The dispatcher uses a network-wide arrival rate `lambda_per_sim_s`.
- Default baseline is `200 / 3600` orders per simulation-second.
- In the Streamlit app, this is multiplied by the `demand_scale` slider.

### Tick rule

For each simulation tick:

1. Compute expected arrivals:

`expected = lambda_per_sim_s * dt_sim_s + leftover`

2. Spawn the integer part immediately:

`n_arrivals = int(expected)`

3. Carry forward the fractional remainder:

`leftover = expected - n_arrivals`

4. Apply stochastic rounding:
   - with probability `leftover`, spawn one additional drone
   - if that happens, leftover resets to `0`

This is not a full Poisson sampler, but it is a stable arrival approximation that preserves the expected mean over time.

### Corridor assignment rule

Each new order is assigned to a corridor using weighted random selection:

`P(corridor_i) = demand_weight_i / sum(demand_weight_all)`

So the current dispatch policy is demand-weighted, not uniform and not queue-aware.

### Spawn rule

Each spawned order becomes a new `Drone` with:

- a unique incrementing ID
- the selected corridor
- a fixed cruise altitude passed in from the dispatcher

### Pad and craning rule

The registry treats a pad as occupied if a drone is in:

- `LANDING`
- `COOLDOWN`

When a drone finishes descent:

- if a pad is free at the destination hub, it enters `COOLDOWN`
- if no pad is free, it enters `CRANING`

While craning:

- the drone waits in the air
- it retries every tick
- once a pad becomes free, it moves into `COOLDOWN`

This is the main bridge between the simulation and the M/G/k analysis: craning is the visible failure mode the pad-sizing model is trying to suppress.

## 6. Current Verified Outputs

### Corridor pruning

Smoke-run result:

- 132 total directed corridors scored
- 77 passed all filters
- 20 retained in final shortlist
- all 132 still use stub assumptions

Top corridor:

- `Hub 11 -> Hub 9`
- drone time: `4.3 min`
- ground time: `10.4 min`
- time saved: `6.1 min`

### Hub sizing, manual service scenario

Current verified result:

- 10 active hubs sized
- 53 landing pads
- 53 battery bays

Heavy hubs:

- Hub 1
- Hub 11
- Hub 2
- Hub 6
- Hub 7

### Hub sizing, automated swap implication

The code still supports the faster automated service spec:

- manual scenario total: `53 pads`
- automated scenario total from project docs: `37 pads`
- strategic reduction: `16 pads`, about `30%`

This remains one of the clearest business-level outputs in the repo.

## 7. Practical Run Order For Later Use

If someone needs to resume work later, the right order is:

1. Restore or provide the three raw SF CSV files expected by `main.py`.
2. Run the data loaders to regenerate the building and residential GeoJSON artifacts.
3. Run hub siting and walk-zone scoring to confirm the canonical hubs or refresh them.
4. Run corridor pruning to regenerate the top-20 shortlist.
5. Run hub sizing on that shortlist.
6. Launch the Streamlit simulation to inspect craning and pad utilisation behavior.

Useful commands:

```bash
python3 main.py --skip-street-network
```

```bash
./.venv/bin/python -c "from corridor_pruning.pruning import prune_corridors; prune_corridors()"
```

```bash
./.venv/bin/python -c "from corridor_pruning.pruning import prune_corridors; from hub_sizing.sizing import size_hubs; size_hubs(prune_corridors())"
```

```bash
./.venv/bin/streamlit run simulation/app.py
```

If `uv` is available in a future environment, the documented `uv run ...` equivalents are fine.

## 8. What Is Stubbed Or Missing

These are still the main accuracy blockers:

1. Per-route obstacle height
   - corridors still use fallback cruise altitude instead of intersecting flight paths with building footprints

2. Real OSMnx path routing
   - the graph loader exists, but `ground_model.py` does not yet use live shortest paths

3. Time-of-day traffic multiplier
   - currently fixed at `1.0`, so Friday congestion is not really modeled

4. Real NHPP demand
   - demand is still a flat peak-rate approximation, not a time-varying fitted process

5. Real service-time measurements
   - kiosk service mean and variance are assumed, not measured

6. Rebalancing integration
   - rebalancing logic exists separately but is not active in the live simulation

7. Dependency metadata
   - `siting_strategy/walk_zones.py` and `optimization.py` import `scipy`, but `pyproject.toml` does not list `scipy`

## 9. Recommended Next Steps

Highest leverage next actions:

1. Implement obstacle-height lookup per corridor from the buildings GeoJSON.
2. Wire OSMnx route timing into `ground_model.py`.
3. Add a real Friday traffic multiplier.
4. Replace flat demand with hub-level NHPP buckets.
5. Measure service-time mean and variance on a prototype workflow.
6. Decide whether the hard-coded 12 hubs stay canonical or should be regenerated automatically.
7. Integrate `simulation/rebalancing.py` if finite-fleet balancing is now in scope.
8. Add `scipy` to `pyproject.toml`.

## 10. Bottom Line

Sky Burrito is currently a strong prototype research codebase with a credible analytical spine:

`spatial data -> hub siting -> corridor ranking -> queue-based hub sizing -> live dispatch simulation`

The architecture is already good. The limiting factor is no longer structure; it is calibration. Once the stubbed obstacle, traffic, demand, and service inputs are replaced with measured or route-specific data, this project can move from a convincing prototype to a much more defensible operational planning tool.
