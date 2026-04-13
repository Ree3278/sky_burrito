"""
K-Means hub siting.

Fits a K-Means model on restaurant coordinates to find the "center of gravity"
for high-density supply clusters. The resulting cluster centers become the
candidate coordinates for rooftop Launch Hubs.

Bimodal strategy (Phase 2):
  - Source hubs  → cluster on restaurant density (this module)
  - Sink hubs    → cluster on residential unit centroids (use load_residential)
"""

from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
from sklearn.cluster import KMeans


@dataclass
class HubModel:
    """Container for a fitted K-Means hub layout."""

    n_clusters: int
    cluster_centers: np.ndarray          # shape (n_clusters, 2) — [lon, lat]
    cluster_labels: np.ndarray           # per-restaurant cluster assignment
    restaurants_per_hub: np.ndarray      # shape (n_clusters,) — raw count
    kmeans: KMeans = field(repr=False)


def fit_hubs(restaurants: gpd.GeoDataFrame, n_clusters: int = 12) -> HubModel:
    """
    Fit a K-Means model on restaurant point coordinates and return a HubModel.

    Parameters
    ----------
    restaurants : GeoDataFrame
        Output of data_processing.load_restaurants(). Must have a Point geometry
        column in EPSG:4326.
    n_clusters : int
        Number of Launch Hubs to site. Default 12 (project spec).

    Returns
    -------
    HubModel
    """
    coords = np.array([(geom.x, geom.y) for geom in restaurants.geometry])

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)
    centers = kmeans.cluster_centers_

    # Count how many restaurants are assigned to each hub
    restaurants_per_hub = np.bincount(labels, minlength=n_clusters)

    print(f"[clustering] Fitted {n_clusters} hubs on {len(restaurants)} restaurants.")
    print("Hub locations (lat, lon):")
    for i, c in enumerate(centers):
        print(f"  Hub {i + 1:2d}: ({c[1]:.6f}, {c[0]:.6f})  — {restaurants_per_hub[i]} restaurants")

    return HubModel(
        n_clusters=n_clusters,
        cluster_centers=centers,
        cluster_labels=labels,
        restaurants_per_hub=restaurants_per_hub,
        kmeans=kmeans,
    )
