"""
5-minute walk zone scoring for candidate hub/kiosk sites.

A kiosk site's "Residential Gravity" is the total residential unit count
within a 420-meter radius (5 min × 1.4 m/s walking speed). This lets us
rank sites by how many customers they passively serve.
"""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from scipy.spatial.distance import cdist

from .clustering import HubModel

# Walk zone constants
WALK_SPEED_MS = 1.4          # average pedestrian speed, m/s
WALK_DISTANCE_MINUTES = 5
WALK_DISTANCE_METERS = WALK_SPEED_MS * 60 * WALK_DISTANCE_MINUTES   # 420 m
WALK_DISTANCE_DEGREES = WALK_DISTANCE_METERS / 111_000               # ≈ 0.00378°


@dataclass
class WalkZoneScores:
    """Per-hub walk zone coverage metrics."""

    n_clusters: int
    restaurants_within_walk: np.ndarray   # count of restaurants within walk zone
    residential_within_walk: np.ndarray   # count of parcels within walk zone
    units_within_walk: np.ndarray         # total resunits within walk zone
    hub_to_restaurants: np.ndarray        # distance matrix (hubs × restaurants)
    hub_to_residential: np.ndarray        # distance matrix (hubs × parcels)


def score_walk_zones(
    hub_model: HubModel,
    restaurants: gpd.GeoDataFrame,
    residential: gpd.GeoDataFrame,
) -> WalkZoneScores:
    """
    Calculate 5-minute walk zone coverage for every hub in a HubModel.

    Parameters
    ----------
    hub_model : HubModel
        Fitted hub layout from siting_strategy.fit_hubs().
    restaurants : GeoDataFrame
        Active food businesses from data_processing.load_restaurants().
    residential : GeoDataFrame
        Residential centroids from data_processing.load_residential().
        Must contain a 'resunits' column.

    Returns
    -------
    WalkZoneScores
    """
    centers = hub_model.cluster_centers
    restaurant_coords = np.array([(g.x, g.y) for g in restaurants.geometry])
    residential_coords = np.array([(g.x, g.y) for g in residential.geometry])

    hub_to_restaurants = cdist(centers, restaurant_coords, metric="euclidean")
    hub_to_residential = cdist(centers, residential_coords, metric="euclidean")

    restaurants_within_walk = (hub_to_restaurants < WALK_DISTANCE_DEGREES).sum(axis=1)
    residential_within_walk = (hub_to_residential < WALK_DISTANCE_DEGREES).sum(axis=1)

    units_within_walk = np.array([
        residential[hub_to_residential[i] < WALK_DISTANCE_DEGREES]["resunits"].sum()
        for i in range(hub_model.n_clusters)
    ])

    print(f"\n[walk_zones] 5-Minute Walk Zone Coverage ({WALK_DISTANCE_METERS:.0f} m radius)")
    print(f"{'Hub':<6} {'Restaurants':>12} {'Res. Units':>12}")
    print("-" * 32)
    total_units = residential["resunits"].sum()
    for i in range(hub_model.n_clusters):
        print(
            f"Hub {i + 1:<2}  {restaurants_within_walk[i]:>10}"
            f"  {units_within_walk[i]:>10,.0f}"
            f"  ({units_within_walk[i] / total_units * 100:.1f}%)"
        )

    return WalkZoneScores(
        n_clusters=hub_model.n_clusters,
        restaurants_within_walk=restaurants_within_walk,
        residential_within_walk=residential_within_walk,
        units_within_walk=units_within_walk,
        hub_to_restaurants=hub_to_restaurants,
        hub_to_residential=hub_to_residential,
    )
