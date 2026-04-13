Here's where the project stands as of today.

---

## Sky Burrito — State of the Union
**April 12, 2026**

### What we set out to do

Prove that drones beat ground couriers on specific, high-value corridors in SF's Mission–Noe Valley pocket — not everywhere, just where topography and gridlock create enough "Topographical Arbitrage" to justify the infrastructure.

---

### What's been built

**The codebase is now a proper Python project.** We went from two unstructured Jupyter notebooks to a `uv`-managed package with three well-separated modules:

**`data_processing/`** handles everything touching raw city data. Five files — `config.py` (bounding box), `restaurants.py`, `buildings.py`, `residential.py`, and `street_network.py` — each expose a single clean loader function. Running them against the three SF Open Data CSVs yields: 927 active food businesses, 15,559 building obstacle polygons, and 13,043 residential parcel centroids, all clipped to the same bounding box.

**`siting_strategy/`** is the spatial analysis layer. `clustering.py` fits K-Means on restaurant coordinates to produce hub candidates. `walk_zones.py` scores each hub by residential units within the 5-minute (420 m) walk radius. `optimization.py` sweeps k ∈ {4, 5, 6, 7, 8, 10, 12} to find the best cluster count. `visualization.py` generates the four key charts. The 12 hub locations are now locked in from actual model output.

**`corridor_pruning/`** is the newest and most technically interesting layer. It hard-codes the 12 hubs with their full match-score data, generates all 132 directed hub-to-hub pairs, runs a drone flight model (climb + cruise + descend, with E=mgh energy cost) against a ground courier model (detour factor + intersection delays + traffic), and filters down to a ranked top-20 shortlist using a composite score of time delta × log(demand) × energy ratio. The pruner runs end-to-end today and produces a working shortlist — Hub 11 → Hub 9 currently leads at 6.1 minutes saved.

---

### Current shortlist (stub model)

The top-20 corridors are computed, but every result is flagged with ⚠ because three stubs are active. The rankings will shift once real data replaces them.

---

### What's missing — the honest gaps

There are four inputs the model is currently faking, in priority order:

**Per-route obstacle heights** is the most critical gap. Every one of the 132 corridors is flying at an assumed 120 m altitude right now. The `mission_noe_buildings.geojson` file already exists on disk from the data processing stage — what's needed is a spatial intersection function that draws a `LineString` between two hubs and returns the tallest building underneath it. A flat corridor over Dolores Park might only need 30 m; one crossing a dense block on 16th might need 80 m. The climb energy difference between those two is roughly 3× and will reshuffle the ranking.

**Real OSMnx ground times** is next. The ground model currently applies a fixed 1.55× detour factor and 30 km/h average speed uniformly. The OSMnx code block in `ground_model.py` is already stubbed and waiting — it just needs the street graph `G` passed in. Without it, efficient flat corridors (Hub 3 → Hub 10 along Valencia) look worse than they are, and hilly ones look better.

**Friday night traffic multiplier** is currently set to 1.0 — no congestion at all. Real Friday evening speeds in the Mission drop to 8–12 km/h, which could push the multiplier to 1.5–2.5×. This is the single biggest lever on time arbitrage and the main reason this whole project makes economic sense.

**Confirmed drone specs** is the lowest-priority gap. The model defaults to a DJI Matrice 350 RTK class (9 kg, 15 m/s, 350 W). A lighter platform would shift the energy crossover point.

---

### What's next

The immediate priority is closing gap #1 — the obstacle height function. That's pure GeoPandas work against data we already have, and it will make the corridor rankings trustworthy enough to present. After that, piping in the OSMnx graph and a traffic multiplier (even a rough one from Uber Movement) gets the model to MVP quality. At that point the pruned corridor list is defensible and the project can move into the M/G/k queuing phase — figuring out how many landing pads each hub actually needs to handle Friday night surge without craning.