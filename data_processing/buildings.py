"""
Load and clean the SF Building Footprints dataset.

Source: Building_Footprints_<date>.csv
Output: GeoDataFrame of 3-D building obstacles (height ≥ 2 m) clipped to the
        project bounding box, saved as mission_noe_buildings.geojson.

Used downstream to calculate per-route Climb Cost:
  E_climb = m * g * h_obstacle_clearance
"""

import geopandas as gpd
import pandas as pd
from shapely import wkt

from .config import BBOX

# Minimum height to qualify as a drone obstacle
_HEIGHT_THRESHOLD_M = 2.0


def load_buildings(csv_path: str, save_geojson: str = "mission_noe_buildings.geojson") -> gpd.GeoDataFrame:
    """
    Read the SF Building Footprints CSV and return obstacle polygons within
    the project bounding box.

    Parameters
    ----------
    csv_path : str
        Path to the raw Building Footprints CSV.
    save_geojson : str, optional
        If provided, write the result to this GeoJSON path.

    Returns
    -------
    gdf : GeoDataFrame
        Columns: hgt_median_m, geometry (Polygon, EPSG:4326)
    """
    columns_to_load = ["shape", "hgt_median_m"]

    df = pd.read_csv(csv_path, usecols=columns_to_load, low_memory=False)

    # Drop rows missing geometry or height
    df = df.dropna(subset=["shape", "hgt_median_m"])

    # Filter out sub-threshold structures (fences, curbs, etc.)
    df = df[df["hgt_median_m"] > _HEIGHT_THRESHOLD_M]

    # Convert WKT to geometry
    df["geometry"] = df["shape"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # Clip to bounding box
    gdf = gdf.cx[BBOX["MIN_LON"]: BBOX["MAX_LON"], BBOX["MIN_LAT"]: BBOX["MAX_LAT"]]
    gdf = gdf[["hgt_median_m", "geometry"]]

    if save_geojson:
        gdf.to_file(save_geojson, driver="GeoJSON")
        print(f"[buildings] Saved {len(gdf)} obstacles → {save_geojson}")
    else:
        print(f"[buildings] Loaded {len(gdf)} building obstacles in corridor.")

    return gdf.reset_index(drop=True)
