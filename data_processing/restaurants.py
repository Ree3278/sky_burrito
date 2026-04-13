"""
Load and clean the SF Registered Business Locations dataset.

Source: Registered_Business_Locations_-_San_Francisco_<date>.csv
Output: GeoDataFrame of active food-service businesses (NAICS 722*) clipped
        to the project bounding box.
"""

import geopandas as gpd
import pandas as pd
from shapely import wkt

from .config import BBOX


def load_restaurants(csv_path: str) -> gpd.GeoDataFrame:
    """
    Read the SF business registry CSV and return active food businesses
    within the project bounding box.

    Parameters
    ----------
    csv_path : str
        Path to the raw SF Registered Business Locations CSV.

    Returns
    -------
    gdf : GeoDataFrame
        Columns: DBA Name, Street Address, NAICS Code, geometry (Point, EPSG:4326)
    """
    columns_to_load = [
        "DBA Name",
        "Street Address",
        "Business End Date",
        "Location End Date",
        "Administratively Closed",
        "NAICS Code",
        "Business Location",
    ]

    df = pd.read_csv(csv_path, usecols=columns_to_load, low_memory=False)

    # Drop rows with no GPS data
    df = df.dropna(subset=["Business Location"])
    if "Latitude" in df.columns and "Longitude" in df.columns:
        df = df.dropna(subset=["Latitude", "Longitude"])

    # Keep only currently active businesses
    df = df[
        df["Business End Date"].isna()
        & df["Location End Date"].isna()
        & df["Administratively Closed"].isna()
    ]

    # Keep only food-service businesses (NAICS sector 722 — Food Services and Drinking Places)
    df = df[df["NAICS Code"].astype(str).str.startswith("722")]

    # Convert WKT string to geometry and build GeoDataFrame
    df["geometry"] = df["Business Location"].apply(wkt.loads)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    # Clip to bounding box
    gdf = gdf.cx[BBOX["MIN_LON"]: BBOX["MAX_LON"], BBOX["MIN_LAT"]: BBOX["MAX_LAT"]]
    gdf = gdf[["DBA Name", "Street Address", "NAICS Code", "geometry"]]

    print(f"[restaurants] Found {len(gdf)} active food businesses in corridor.")
    return gdf.reset_index(drop=True)
