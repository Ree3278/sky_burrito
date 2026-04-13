"""
Hub count sweep — find the optimal number of K-Means clusters.

Iterates over a range of candidate cluster counts and reports residential unit
coverage percentage for each. The recommended count is the smallest k that
achieves ≥50% coverage, balancing infrastructure cost against market reach.
"""

from dataclasses import dataclass
from typing import List

import geopandas as gpd
import numpy as np
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans

from .walk_zones import WALK_DISTANCE_DEGREES

_DEFAULT_CLUSTER_COUNTS = [4, 5, 6, 7, 8, 10, 12]
_COVERAGE_TARGET = 0.50   # recommend the smallest k hitting this threshold


@dataclass
class ClusterSweepResult:
    """Coverage metrics for a single cluster count."""

    n_clusters: int
    total_units_covered: float
    coverage_pct: float
    avg_units_per_hub: float


def sweep_cluster_counts(
    restaurants: gpd.GeoDataFrame,
    residential: gpd.GeoDataFrame,
    cluster_counts: List[int] = _DEFAULT_CLUSTER_COUNTS,
) -> List[ClusterSweepResult]:
    """
    Fit K-Means for each value in cluster_counts and measure residential
    unit coverage within the 5-minute walk zone.

    Parameters
    ----------
    restaurants : GeoDataFrame
        Active food businesses (supply points for hub clustering).
    residential : GeoDataFrame
        Residential centroids with 'resunits' column (demand points).
    cluster_counts : list of int
        Hub counts to evaluate.

    Returns
    -------
    results : list of ClusterSweepResult
        One entry per cluster count, sorted by n_clusters ascending.
    """
    restaurant_coords = np.array([(g.x, g.y) for g in restaurants.geometry])
    residential_coords = np.array([(g.x, g.y) for g in residential.geometry])
    total_units = residential["resunits"].sum()

    print(f"\n[optimization] Sweeping cluster counts: {cluster_counts}")
    print(f"{'k':>4}  {'Coverage':>10}  {'Total Units':>12}  {'Avg/Hub':>10}")
    print("-" * 42)

    results = []
    for k in cluster_counts:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(restaurant_coords)
        centers = km.cluster_centers_

        hub_to_res = cdist(centers, residential_coords, metric="euclidean")
        units_covered = sum(
            residential[hub_to_res[i] < WALK_DISTANCE_DEGREES]["resunits"].sum()
            for i in range(k)
        )
        coverage_pct = units_covered / total_units
        avg_per_hub = units_covered / k

        results.append(ClusterSweepResult(
            n_clusters=k,
            total_units_covered=units_covered,
            coverage_pct=coverage_pct,
            avg_units_per_hub=avg_per_hub,
        ))
        print(
            f"{k:>4}  {coverage_pct:>9.1%}  {units_covered:>12,.0f}  {avg_per_hub:>10,.0f}"
        )

    # Recommend smallest k meeting the coverage target
    candidates = [r for r in results if r.coverage_pct >= _COVERAGE_TARGET]
    if candidates:
        rec = min(candidates, key=lambda r: r.n_clusters)
        print(
            f"\n[optimization] Recommended: {rec.n_clusters} hubs "
            f"({rec.coverage_pct:.1%} coverage, {rec.total_units_covered:,.0f} units)"
        )
    else:
        print(
            f"\n[optimization] No configuration reaches {_COVERAGE_TARGET:.0%} coverage. "
            "Consider expanding the bounding box or relaxing the walk-zone radius."
        )

    return results
