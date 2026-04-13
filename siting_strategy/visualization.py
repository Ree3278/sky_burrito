"""
Visualization functions for hub siting analysis.

All functions save a PNG to disk and return the (fig, ax) tuple so callers
can further customize or display inline in a notebook.
"""

import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd

from .clustering import HubModel
from .walk_zones import WalkZoneScores, WALK_DISTANCE_DEGREES, WALK_DISTANCE_METERS


# ---------------------------------------------------------------------------
# Building height distribution
# ---------------------------------------------------------------------------

def plot_building_heights(
    buildings: gpd.GeoDataFrame,
    out_path: str = "03_building_height_distribution.png",
):
    """
    Histogram + box plot of building heights in the corridor.

    Outputs a recommended minimum cruising altitude (max height + 50 m buffer).

    Parameters
    ----------
    buildings : GeoDataFrame
        Output of data_processing.load_buildings(). Must have 'hgt_median_m'.
    out_path : str
        File path for the saved PNG.
    """
    heights = buildings["hgt_median_m"].values

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    # Histogram
    ax1 = axes[0]
    ax1.hist(heights, bins=50, color="#3498db", edgecolor="black", alpha=0.7)
    ax1.axvline(heights.mean(), color="red", linestyle="--", linewidth=2,
                label=f"Mean: {heights.mean():.1f} m")
    ax1.axvline(np.median(heights), color="green", linestyle="--", linewidth=2,
                label=f"Median: {np.median(heights):.1f} m")
    ax1.set_xlabel("Building Height (m)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Frequency", fontsize=11, fontweight="bold")
    ax1.set_title("Building Height Distribution\n(Drone Must Clear Max Height)",
                  fontsize=12, fontweight="bold")
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3, axis="y")

    # Box plot
    ax2 = axes[1]
    bp = ax2.boxplot([heights], labels=["All Buildings"], patch_artist=True)
    bp["boxes"][0].set_facecolor("#3498db")
    ax2.set_ylabel("Height (m)", fontsize=11, fontweight="bold")
    ax2.set_title("Building Height Statistics", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3, axis="y")

    stats_text = (
        f"Total Buildings: {len(buildings)}\n"
        f"Min: {heights.min():.1f} m\n"
        f"Max: {heights.max():.1f} m  ← BOTTLENECK\n"
        f"Mean: {heights.mean():.1f} m\n"
        f"Median: {np.median(heights):.1f} m\n"
        f"Std Dev: {heights.std():.1f} m\n\n"
        f"Min Cruise Alt: {heights.max() + 50:.1f} m\n"
        f"(max + 50 m safety buffer)"
    )
    ax2.text(1.3, heights.max() * 0.8, stats_text, fontsize=10,
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
             verticalalignment="top", family="monospace")

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()

    print(f"[viz] Saved → {out_path}")
    print(f"      Max building height: {heights.max():.1f} m")
    print(f"      Recommended min cruising altitude: {heights.max() + 50:.1f} m")
    return fig, axes


# ---------------------------------------------------------------------------
# Supply / demand density maps
# ---------------------------------------------------------------------------

def plot_density_maps(
    restaurants: gpd.GeoDataFrame,
    residential: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    out_path: str = "05a_separate_density_maps.png",
):
    """
    Side-by-side restaurant density map and residential density map (no hubs).

    Parameters
    ----------
    restaurants, residential, buildings : GeoDataFrame
        Outputs of the data_processing loaders.
    out_path : str
        File path for the saved PNG.
    """
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    # Left — restaurant supply
    ax_rest = axes[0]
    buildings.plot(ax=ax_rest, color="lightgray", alpha=0.4, edgecolor="gray", linewidth=0.2)
    ax_rest.scatter(restaurants.geometry.x, restaurants.geometry.y,
                    c="#e74c3c", s=120, alpha=0.7, marker="^",
                    edgecolors="darkred", linewidth=1, label="Restaurants")
    ax_rest.set_xlabel("Longitude", fontsize=12, fontweight="bold")
    ax_rest.set_ylabel("Latitude", fontsize=12, fontweight="bold")
    ax_rest.set_title(f"Restaurant Supply Density\n({len(restaurants)} restaurants)",
                      fontsize=13, fontweight="bold")
    ax_rest.legend(loc="upper right", fontsize=11)
    ax_rest.grid(True, alpha=0.2)

    # Right — residential demand
    ax_res = axes[1]
    buildings.plot(ax=ax_res, color="lightgray", alpha=0.4, edgecolor="gray", linewidth=0.2)
    sc = ax_res.scatter(residential.geometry.x, residential.geometry.y,
                        c=residential["resunits"], cmap="RdYlGn", s=120, alpha=0.7,
                        edgecolors="darkgreen", linewidth=1)
    plt.colorbar(sc, ax=ax_res, label="Residential Units")
    ax_res.set_xlabel("Longitude", fontsize=12, fontweight="bold")
    ax_res.set_ylabel("Latitude", fontsize=12, fontweight="bold")
    ax_res.set_title(f"Residential Demand Density\n({len(residential)} properties)",
                     fontsize=13, fontweight="bold")
    ax_res.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()
    print(f"[viz] Saved → {out_path}")
    return fig, axes


def plot_supply_demand_overlay(
    restaurants: gpd.GeoDataFrame,
    residential: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    out_path: str = "05a_overlay_supply_demand_map.png",
):
    """
    Single combined map: building obstacles + residential heat + restaurant points.

    Parameters
    ----------
    restaurants, residential, buildings : GeoDataFrame
    out_path : str
    """
    fig, ax = plt.subplots(figsize=(16, 12))

    buildings.plot(ax=ax, color="#e8e8e8", alpha=0.5, edgecolor="#999999",
                   linewidth=0.3, label="Building Obstacles")

    sc = ax.scatter(residential.geometry.x, residential.geometry.y,
                    c=residential["resunits"], cmap="YlGn", s=80, alpha=0.6,
                    edgecolors="darkgreen", linewidth=0.5,
                    label=f"Residential (n={len(residential)})")

    ax.scatter(restaurants.geometry.x, restaurants.geometry.y,
               c="#e74c3c", s=100, alpha=0.8, marker="^",
               edgecolors="darkred", linewidth=1,
               label=f"Restaurants (n={len(restaurants)})", zorder=5)

    plt.colorbar(sc, ax=ax, label="Residential Units per Property", pad=0.02)
    ax.set_xlabel("Longitude", fontsize=12, fontweight="bold")
    ax.set_ylabel("Latitude", fontsize=12, fontweight="bold")
    ax.set_title("Supply + Demand Overlap\n(Restaurants overlaid on Residential Density)",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=11, framealpha=0.95)
    ax.grid(True, alpha=0.2, linestyle="--")

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()
    print(f"[viz] Saved → {out_path}")
    return fig, ax


# ---------------------------------------------------------------------------
# Walk zone map
# ---------------------------------------------------------------------------

def plot_walk_zones(
    hub_model: HubModel,
    walk_scores: WalkZoneScores,
    restaurants: gpd.GeoDataFrame,
    residential: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    out_path: str = "05b_5min_walk_distance_analysis.png",
):
    """
    Two-panel plot: walk-zone circles on the map + per-hub coverage bar chart.

    Parameters
    ----------
    hub_model : HubModel
        Fitted hub layout.
    walk_scores : WalkZoneScores
        Walk zone scoring results.
    restaurants, residential, buildings : GeoDataFrame
    out_path : str
    """
    centers = hub_model.cluster_centers
    n = hub_model.n_clusters
    colors = plt.cm.Set1(np.linspace(0, 1, n))

    fig = plt.figure(figsize=(18, 7))

    # --- Left: map with walk-zone circles ---
    ax1 = plt.subplot(1, 2, 1)
    buildings.plot(ax=ax1, color="lightgray", alpha=0.4, edgecolor="gray", linewidth=0.2)

    ax1.scatter(restaurants.geometry.x, restaurants.geometry.y,
                c="#e74c3c", s=60, alpha=0.6, marker="^",
                edgecolors="darkred", linewidth=0.5, label="Restaurants")
    ax1.scatter(residential.geometry.x, residential.geometry.y,
                c="#2ecc71", s=40, alpha=0.5,
                edgecolors="darkgreen", linewidth=0.5, label="Residential")

    for i, (center, color) in enumerate(zip(centers, colors)):
        # Filled zone
        ax1.add_patch(plt.Circle(
            (center[0], center[1]), WALK_DISTANCE_DEGREES,
            color=color, fill=True, alpha=0.15,
        ))
        # Outline
        ax1.add_patch(plt.Circle(
            (center[0], center[1]), WALK_DISTANCE_DEGREES,
            color=color, fill=False, linewidth=2.5, alpha=0.9,
        ))
        # Hub star
        ax1.scatter(center[0], center[1], c=[color], marker="*", s=1500,
                    edgecolors="black", linewidth=2.5, zorder=10)
        ax1.annotate(
            f"Hub {i + 1}", xy=(center[0], center[1]),
            xytext=(8, 8), textcoords="offset points",
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor=color, alpha=0.7),
        )

    ax1.set_xlabel("Longitude", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Latitude", fontsize=12, fontweight="bold")
    ax1.set_title(
        f"5-Minute Walk Zones ({WALK_DISTANCE_METERS:.0f} m radius)",
        fontsize=13, fontweight="bold",
    )
    ax1.legend(loc="upper left", fontsize=10)
    ax1.grid(True, alpha=0.2)

    # --- Right: bar chart ---
    ax2 = plt.subplot(1, 2, 2)
    x_pos = np.arange(n)
    width = 0.35

    bars1 = ax2.bar(
        x_pos - width / 2, walk_scores.restaurants_within_walk, width,
        label="Restaurants (5-min walk)", color="#e74c3c", alpha=0.85,
        edgecolor="darkred", linewidth=1.5,
    )
    bars2 = ax2.bar(
        x_pos + width / 2, walk_scores.units_within_walk / 100, width,
        label="Residential Units ÷ 100", color="#2ecc71", alpha=0.85,
        edgecolor="darkgreen", linewidth=1.5,
    )

    for bars in (bars1, bars2):
        for bar in bars:
            h = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, h,
                     f"{int(h)}", ha="center", va="bottom",
                     fontsize=10, fontweight="bold")

    ax2.set_xlabel("Launch Hub", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Count", fontsize=12, fontweight="bold")
    ax2.set_title("Coverage Within 5-Minute Walk", fontsize=13, fontweight="bold")
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([f"Hub {i + 1}" for i in range(n)], fontsize=11)
    ax2.legend(fontsize=11, loc="upper right")
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()
    print(f"[viz] Saved → {out_path}")
    return fig, (ax1, ax2)
