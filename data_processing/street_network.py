"""
Download the drivable street graph for the project corridor via OSMnx.

The street graph is the ground-transit benchmark used to calculate
Topographical Arbitrage:

  arbitrage(route) = t_car(OSMnx shortest path) - t_drone(straight-line / cruise_speed)

Only routes with a significant time delta are kept in the pruned corridor set.
"""

import osmnx as ox

from .config import BBOX


def load_street_network(network_type: str = "drive"):
    """
    Download and return the OSMnx street graph for the Mission–Noe corridor.

    Handles both OSMnx ≥2.0 (bbox tuple) and older positional-arg APIs.

    Parameters
    ----------
    network_type : str
        OSMnx network type. "drive" excludes pedestrian-only paths.

    Returns
    -------
    G : networkx.MultiDiGraph
        Drivable street graph with nodes (intersections) and edges (road segments).
    """
    north = BBOX["MAX_LAT"]
    south = BBOX["MIN_LAT"]
    east  = BBOX["MAX_LON"]
    west  = BBOX["MIN_LON"]

    print("[street_network] Downloading street graph from OpenStreetMap...")

    try:
        # OSMnx ≥2.0: bbox kwarg expects (west, south, east, north)
        G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type)
    except TypeError:
        # Fallback for OSMnx <2.0: positional order is (north, south, east, west)
        G = ox.graph_from_bbox(north, south, east, west, network_type=network_type)

    print(
        f"[street_network] Downloaded graph: "
        f"{len(G.nodes)} intersections, {len(G.edges)} road segments."
    )
    return G
