"""
Load and clean the SF Land Use dataset.

Source: San_Francisco_Land_Use_-_2023_<date>.csv
Output: GeoDataFrame of residential property centroids with unit counts,
        clipped to the project bounding box, saved as
        mission_noe_residential_sinks.geojson.

Used downstream to score kiosk sites by "Residential Gravity":
  gravity(kiosk) = Σ resunits within 420 m walk zone
"""

import geopandas as gpd
import pandas as pd
from shapely import wkt

from .config import BBOX


def load_residential(
    csv_path: str,
    save_geojson: str = "mission_noe_residential_sinks.geojson",
) -> gpd.GeoDataFrame:
    """
    Read the SF Land Use CSV and return residential parcel centroids within
    the project bounding box.

    Parcel polygons are converted to centroids using Web Mercator (EPSG:3857)
    for metric accuracy, then projected back to WGS-84 (EPSG:4326).

    Parameters
    ----------
    csv_path : str
        Path to the raw SF Land Use CSV.
    save_geojson : str, optional
        If provided, write the result to this GeoJSON path.

    Returns
    -------
    gdf : GeoDataFrame
        Columns: landuse, resunits, geometry (Point centroid, EPSG:4326)
    """
    columns_to_load = ["the_geom", "landuse", "resunits"]

    df = pd.read_csv(csv_path, usecols=columns_to_load, low_memory=False)

    # Drop rows with missing geometry
    df = df.dropna(subset=["the_geom"])

    # Coerce resunits to numeric and keep only residential parcels
    df["resunits"] = pd.to_numeric(df["resunits"], errors="coerce").fillna(0)
    df = df[df["resunits"] > 0]

    # Convert WKT to geometry
    df["geometry"] = df["the_geom"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # Clip to bounding box
    gdf = gdf.cx[BBOX["MIN_LON"]: BBOX["MAX_LON"], BBOX["MIN_LAT"]: BBOX["MAX_LAT"]]

    # Convert polygon footprints to centroids (project to meters for accuracy)
    gdf = gdf.to_crs("EPSG:3857")
    gdf["geometry"] = gdf.geometry.centroid
    gdf = gdf.to_crs("EPSG:4326")

    gdf = gdf[["landuse", "resunits", "geometry"]]

    if save_geojson:
        gdf.to_file(save_geojson, driver="GeoJSON")
        print(f"[residential] Saved {len(gdf)} residential centroids → {save_geojson}")
    else:
        print(f"[residential] Loaded {len(gdf)} residential properties in corridor.")

    return gdf.reset_index(drop=True)
