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
<<<<<<< HEAD
- drone time: `4.3 min`
- ground time: `10.4 min`
- time saved: `6.1 min`

### Hub sizing, manual service scenario

Current verified result:
=======
- drone time: 4.3 min
- car time: 10.4 min
- delta: 6.1 min saved

Other top-ranked corridors are concentrated around Hubs 1, 2, 6, 9, 10, and 11, which strongly suggests the model is already identifying a core operational spine rather than spreading demand evenly.

### Hub sizing

Manual service scenario:
>>>>>>> 543e44e (summary report added)

- 10 active hubs sized
- 53 landing pads
- 53 battery bays
<<<<<<< HEAD

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
=======
- heavy hubs: 1, 11, 2, 6, 7

Automated swap scenario:

- 10 active hubs sized
- 37 landing pads
- 37 battery bays

Main business takeaway:

- automated swap reduces total pad requirement by 16 pads, about 30 percent

That is one of the clearest strategic outputs in the whole repo.

## 6. What Is Working Well

- The repo has successfully evolved from exploratory notebooks into a modular Python project.
- The analytical progression is coherent: raw spatial data -> hub siting -> corridor pruning -> hub sizing -> live simulation.
- The code reflects a clear systems view rather than isolated models.
- The pruning and sizing stages are executable today and produce stable outputs.
- The Streamlit simulation gives the project a strong demonstration layer for stakeholders.
- Documentation in `README.md` and `SOTU/` captures the project narrative well.

## 7. Main Gaps and Risks

### A. Critical modeling inputs are still stubbed

This is the single biggest limitation.

Current placeholders include:

- per-route obstacle height in `corridor_pruning/corridors.py`
- OSMnx-based routing in `corridor_pruning/ground_model.py`
- traffic multiplier in `corridor_pruning/ground_model.py`
- NHPP demand in `hub_sizing/demand.py`
- measured service-time distributions in `hub_sizing/service.py`

Consequence:

- the ranking is directionally useful, but not presentation-grade as a final operational recommendation

### B. Raw input CSVs are not present in the checkout

The repo currently does not contain the three CSV files that `main.py` and the README expect. That means the original siting pipeline is not reproducible from this checkout alone.

Consequence:

- the code structure is ready, but full data regeneration cannot be demonstrated without external files

### C. Dependency metadata is incomplete

Both `siting_strategy/walk_zones.py` and `siting_strategy/optimization.py` import `scipy.spatial.distance.cdist`, but `pyproject.toml` does not declare `scipy`.

Consequence:

- a fresh install from project metadata may fail even though the current venv works

### D. Documentation has one material count mismatch

The README says there are 144 possible hub pairings, but the implemented corridor generator correctly creates 132 directed non-self pairs.

Consequence:

- small documentation mismatch, but it can confuse presentations or review discussions

### E. Rebalancing exists but is not integrated

`simulation/rebalancing.py` is present as an untracked file and does not appear connected to `simulation/app.py`, `simulation/registry.py`, or package exports.

Consequence:

- the repo has a promising Phase 2 direction, but it is not yet part of the official runnable path

## 8. Current Project Maturity

Best description:

- not a finished production model
- not just a class notebook anymore
- currently a strong prototype research codebase with live demonstrator value

Maturity by layer:

- spatial preprocessing: good
- hub siting: good
- corridor ranking: medium, pending real-world calibration
- capacity sizing: medium-good, pending real-world calibration
- simulation UI: promising demo
- operational realism: still in progress

## 9. Recommended Next Steps

Priority order based on project leverage:

1. Implement per-corridor obstacle-height lookup from building footprints.
2. Wire real OSMnx routing into `ground_model.py`.
3. Add a real or defensible traffic multiplier for Friday evening conditions.
4. Add `scipy` to project dependencies.
5. Decide whether the 12 hard-coded hubs should remain canonical or be regenerated from raw data on demand.
6. Integrate `simulation/rebalancing.py` into the live simulation if rebalancing is now part of scope.
7. Add a small smoke-test suite for pruning, sizing, and simulation imports.
8. Clean the docs so implementation details and README numbers match exactly.

## 10. Final Judgement

Sky Burrito is a well-framed urban drone logistics prototype with a clear analytical spine and enough executable code to demonstrate real progress. The project is already valuable as a systems-design artifact, a modeling portfolio piece, and a stakeholder demo. Its current weakness is not lack of architecture; it is lack of calibrated inputs.

If the next round of work focuses on replacing stubs with measured or route-specific data, this project can move from "interesting concept with a convincing prototype" to "defensible corridor and infrastructure recommendation engine."

## 11. Key Evidence References

- Project framing and expected data inputs: `README.md`
- Full siting pipeline entry point: `main.py`
- Walk-zone scoring and optimization: `siting_strategy/walk_zones.py`, `siting_strategy/optimization.py`
- Corridor generation and missing route inputs: `corridor_pruning/corridors.py`, `corridor_pruning/pruning.py`, `corridor_pruning/ground_model.py`
- Hub sizing output logic: `hub_sizing/sizing.py`
- Live simulation prototype: `simulation/app.py`
- Rebalancing extension: `simulation/rebalancing.py`
>>>>>>> 543e44e (summary report added)
