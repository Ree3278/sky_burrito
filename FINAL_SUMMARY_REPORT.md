# Sky Burrito Final Summary Report

Date: April 22, 2026  
Repo: `sky_burrito`

## 1. Executive Summary

Sky Burrito is now an end-to-end prototype for selective drone delivery in San Francisco. The project does not argue that drones should replace all ground delivery. It argues that drones make sense only on a narrow set of high-friction urban corridors, and it builds a full decision chain around that idea:

`geospatial inputs -> hub siting -> corridor pruning -> hub sizing -> finite-fleet simulation -> rebalancing`

The final version is stronger than the earlier analytical drafts because the system no longer stops at route ranking. It now models what happens after launch: finite fleet inventory, queue buildup, pad saturation, craning, and drone repositioning across the network. In other words, the project now answers not just "where should drones fly?" but also "how does the network stay operational once demand starts pulling drones out of balance?"

From the current verified run:

- 132 directed hub-to-hub corridors are scored
- 77 pass the pruning filters
- 20 make the final ranked shortlist
- the current top corridor is `Hub 11 -> Hub 9`
- that top corridor saves `6.1 minutes`, about `$7.34` per delivery, and about `99.6%` of ground CO2
- current all-hub M/G/k sizing recommends `86` landing pads and `86` battery bays across `10` active hubs under the present stub demand/service assumptions
- the persisted simulation setup operates on `19` shortlisted routes across `9` active hubs with a modeled peak of about `440 orders/hour`

## 2. Storytelling Summary

If this project is presented without code first, the story is simple:

San Francisco creates delivery friction. Streets bend around hills, traffic compounds delay, and short aerial distances often turn into much longer ground trips. Sky Burrito starts from that mismatch. The project asks where the city is inefficient enough on the ground that a straight-line flight becomes economically and operationally interesting.

That is why the system is intentionally selective. We do not start by drawing drones over the whole map. We start by narrowing the problem:

- place hubs where restaurant supply is strong
- prefer hubs that also serve dense residential demand within a 5-minute walk
- keep only corridors where drones materially beat ground travel
- favor routes where the time advantage also comes with cost and energy advantage
- size infrastructure so the winning network can survive peak demand
- rebalance drones so one busy hub does not run dry while another becomes a parking lot

The final version changes the project narrative in an important way. Earlier, Sky Burrito could identify promising corridors and size hubs, but the last operational question remained open: what happens when demand pulls the fleet unevenly across the city? The new rebalancing layer makes that question visible and manageable. Exporter hubs can starve; importer hubs can accumulate idle drones; pad constraints can turn into craning. The project now has a concrete answer for that final-mile operational problem.

So the best way to frame Sky Burrito is this:

It is not a generic drone demo. It is a selective urban logistics design tool that finds where drones are worth using, estimates the infrastructure they need, and models how a limited fleet behaves once the system goes live.

## 3. Technical Summary

### 3.1 Analytical Pipeline

The repo is organized as a staged modeling chain:

1. `data_processing/`
   - prepares restaurant, building, residential, and street-network inputs inside the Mission-Noe bounding box

2. `siting_strategy/`
   - uses K-Means clustering to place candidate hubs
   - scores each hub by nearby restaurant supply and residential units within a 5-minute walk radius (`420 m`)

3. `corridor_pruning/`
   - generates all directed hub pairs
   - runs drone, ground, cost, and carbon models on each corridor
   - filters and ranks the network down to the best routes

4. `hub_sizing/`
   - converts corridor activity into per-hub demand
   - uses M/G/k queueing to solve for landing pad count and battery bays

5. `simulation/`
   - turns the static shortlist into a live finite-fleet network with queues, pad occupancy, craning, and optional learned rebalancing

6. `rebalancing/`
   - adds the pressure-based "ghost" heuristic that complements learned fleet control inside the RL environment

### 3.2 Corridor Scoring

The pruning stage is now more than a time-saved filter. Each corridor carries:

- flight time from `drone_model.py`
- ground travel time and Uber-style payout from `ground_model.py` and `driver_economics.py`
- carbon savings from `carbon_footprint.py`
- a demand proxy:

`demand_weight = origin.restaurants_nearby * destination.resunits_nearby`

Current hard filters:

- `time_delta_s >= 120`
- `energy_ratio > 1.0`
- `demand_weight >= 100000`

Current ranking logic in `corridor_pruning/pruning.py` uses a weighted composite where cost is dominant:

- `60%` cost arbitrage
- `20%` time advantage
- `20%` energy advantage

That matches the actual final code better than the older report versions, which described a simpler time-log-demand formula.

### 3.3 Hub Sizing

The hub-sizing layer converts shortlisted corridor flow into peak-hour arrivals and solves the minimum pad count `k` such that:

- `P(craning) <= 5%`
- utilization `<= 85%`

The default manual service assumption is still:

`30 + 60 + 180 + 60 = 330 seconds`

So the sizing stage is still a modeled operational estimate, not yet a measured field-service estimate. Even so, it gives the project one of its strongest practical outputs: a per-hub infrastructure recommendation instead of a vague network sketch.

### 3.4 Final Simulation Architecture

The simulation is now a real finite-fleet operational model.

`simulation/fleet.py`
- keeps exact drone inventory per hub
- queues orders when no idle drone is available
- reallocates returned drones back into the pool

`simulation/dispatcher.py`
- generates payload requests on shortlisted corridors
- modulates demand by time of day using meal windows rather than a flat constant peak

`simulation/registry.py`
- acts as the central loop
- launches payload flights
- advances drone state
- counts pad occupancy
- detects craning events
- supports cross-hub fallback when the designated origin hub is empty

`simulation/drone.py`
- models each payload drone as a finite state machine:

`IDLE -> TAKEOFF -> CRUISE -> LANDING -> COOLDOWN -> IDLE`

with `CRANING` as the failure state when a destination pad is unavailable

`simulation/app.py`
- exposes the network as a Streamlit + Pydeck digital twin with live hub utilization, queue depth, drone states, and featured-route storytelling

### 3.5 Rebalancing: What Was Added In The Final Version

This is the most important architectural change since the earlier summary draft.

The project now contains three related rebalancing layers:

1. `simulation/rl_fleet_env.py`
   - the Gymnasium training environment
   - models a `42D` observation and `9D` continuous action space
   - includes both learned rebalancing and the pressure-based ghost heuristic

2. `rebalancing/ghost_logic.py`
   - computes target idle inventory by hub from base demand rates
   - computes hub pressure:

`pressure = idle - queue - target`

   - matches donor hubs to recipient hubs by shortest flight time
   - applies guardrails:
     - battery floor
     - recipient utilization safety check
     - dinner-rush suppression from `18:00` to `20:00`

3. `simulation/rl_bridge.py`
   - brings trained PPO behavior into the live Streamlit simulation
   - performs behind-the-scenes inventory moves in the fleet pool
   - now routes rebalancing moves toward the highest-pressure hub instead of blindly cycling hub-to-hub

There is also a smaller experimental helper in `simulation/rebalancing.py` that implements exact integer target allocation plus a deterministic `DemandRebalancer`. It reads as a compact policy sandbox. The more fully integrated final rebalancing path, however, is the combination of `rl_fleet_env.py`, `rebalancing/ghost_logic.py`, and `simulation/rl_bridge.py`.

Operationally, this matters because the project can now model tidal flow, not just static route quality. Some hubs export drones through repeated payload launches while others accumulate them. Rebalancing is what makes the finite-fleet system sustainable instead of fragile.

## 4. Current Verified Status

This report was updated from the current source code and a local verification pass on April 22, 2026.

### 4.1 Successful Checks

Using `./.venv/bin/python` from repo root:

- `corridor_pruning.prune_corridors()` runs successfully
- `hub_sizing.size_hubs(prune_corridors())` runs successfully
- `simulation.app`, `simulation.rebalancing`, and `simulation.rl_fleet_env` import successfully
- `PYTHONPATH=. ./.venv/bin/python testing/test_enhancements.py` passes
- `load_or_build_simulation_setup()` builds a current runtime setup with:
  - `19` routes
  - `9` active hubs
  - `440` peak orders/hour

### 4.2 Verified Corridor Output

Current pruning output:

- total scored: `132`
- passed filters: `77`
- final shortlist: `20`
- routes still using stub assumptions: `132`

Top route:

- corridor: `Hub 11 -> Hub 9`
- straight-line distance: `2.40 km`
- time savings: `6.1 min`
- Uber ground payout: `$7.36`
- drone cost: `$0.03`
- cost arbitrage: `$7.34`
- carbon savings: `0.682 kg CO2` per delivery
- carbon reduction: `99.6%`

### 4.3 Verified Hub-Sizing Output

Current all-shortlist sizing result under the default stub demand/service model:

- active hubs sized: `10`
- network total: `86` landing pads
- network total: `86` battery bays

Highest-load hubs in the current report:

- Hub 1
- Hub 11
- Hub 2
- Hub 6
- Hub 7
- Hub 9
- Hub 10
- Hub 5

Light hubs in the current report:

- Hub 3
- Hub 4

This is a meaningful update from older summary drafts that cited a smaller `53-pad` network. The current code and present assumptions produce a substantially larger requirement, so the older number should no longer be treated as current.

## 5. Honest Caveats

The project is much stronger now, but it is still honest prototype work rather than a calibrated production planner.

### 5.1 What Still Uses Stubs

- `ground_model.py` still relies on a detour-factor street proxy when no OSMnx routing graph is wired in
- obstacle handling degrades gracefully to fallback cruise altitude when the raw building CSV is unavailable
- demand allocation in `hub_sizing/demand.py` remains modeled rather than platform-derived
- kiosk service times are still assumed, not measured in field operations

### 5.2 Codebase Notes Worth Knowing

- the raw building CSV was not present in this checkout during verification, so corridor results used fallback obstacle heights
- one older regression script, `testing/test_rl_environment_regressions.py`, is currently stale because it imports `ACTIVE_HUBS` from `simulation.rl_fleet_env` even though the active constant now lives in `settings/rl.py`
- `pytest` is not installed in this shell, so verification here used direct Python entrypoints instead of a full pytest run

### 5.3 Interpretation Caution

That means the current outputs are best interpreted as:

- structurally meaningful
- internally consistent
- useful for comparing corridors and exposing operational bottlenecks

but not yet a final real-world business case until traffic, demand, and service-time calibration are replaced with measured inputs.

## 6. Bottom Line

Sky Burrito now has a credible full-stack prototype:

`city data -> hub siting -> corridor economics -> hub infrastructure sizing -> finite-fleet operations -> rebalancing`

The most important final improvement is that the project no longer treats fleet balance as an afterthought. It now models the operational problem that appears once a good route network starts moving real volume: drones drift, hubs starve, queues form, and pads saturate. By adding finite-fleet logic and explicit rebalancing, the repo now tells a much more complete story.

The project is still limited by calibration, but not by architecture. The architecture is now coherent, modular, and close to the right shape for a serious planning tool.

## 7. Key Evidence References

- Project entrypoints: `main.py`, `README.md`
- Environment assembly: `simulation/environment.py`
- Corridor ranking: `corridor_pruning/pruning.py`
- Ground economics: `corridor_pruning/ground_model.py`, `corridor_pruning/driver_economics.py`
- Carbon model: `corridor_pruning/carbon_footprint.py`
- Hub sizing: `hub_sizing/sizing.py`
- Finite fleet + registry loop: `simulation/fleet.py`, `simulation/registry.py`
- Live app: `simulation/app.py`
- RL environment: `simulation/rl_fleet_env.py`
- Live PPO bridge: `simulation/rl_bridge.py`
- Rebalancing heuristic: `rebalancing/ghost_logic.py`
- Deterministic helper policy: `simulation/rebalancing.py`
