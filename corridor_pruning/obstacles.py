"""
Extract building obstacle heights for drone flight planning.

The Building_Footprints_20260410.csv contains ~15k buildings in SF with:
  - shape: WKT polygon geometry
  - gnd_maxcm: Ground maximum elevation (cm)
  - p2010_zmaxn88ft: Max elevation (feet, NAVD88 datum)

We use p2010_zmaxn88ft (converted to meters) as the obstacle height
for corridor clearance calculations.

Note: Requires pandas, geopandas, shapely for full functionality.
This module gracefully degrades when dependencies are missing.
"""

from typing import Optional, List
import warnings

HAS_GEO_DEPS = False
pd = None
gpd = None
wkt = None
LineString = None

try:
    import pandas as pd_temp
    import geopandas as gpd_temp
    from shapely import wkt as wkt_temp
    from shapely.geometry import LineString as LineString_temp
    
    pd = pd_temp
    gpd = gpd_temp
    wkt = wkt_temp
    LineString = LineString_temp
    HAS_GEO_DEPS = True
except ImportError:
    warnings.warn(
        "pandas/geopandas not available; obstacle heights will use fallback (120m). "
        "Install: pip install pandas geopandas shapely"
    )


def load_buildings_gdf(
    csv_path: str = "Building_Footprints_20260410.csv",
    bounds: tuple = None,
):
    """
    Load building footprints and heights into a GeoDataFrame.
    
    Parameters
    ----------
    csv_path : str
        Path to Building_Footprints CSV
    bounds : tuple
        (min_lon, min_lat, max_lon, max_lat) to clip buildings.
        If None, loads all buildings (slow).
    
    Returns
    -------
    GeoDataFrame with columns:
        - geometry: Polygon
        - height_m: Building height in meters (from p2010_zmaxn88ft)
    
    or None if dependencies are missing
    """
    
    if not HAS_GEO_DEPS:
        warnings.warn("pandas/geopandas required for obstacle loading")
        return None
    
    print(f"  📦 Loading buildings from {csv_path}...")
    
    # Read CSV with minimal columns
    try:
        df = pd.read_csv(
            csv_path,
            usecols=['shape', 'p2010_zmaxn88ft'],
            dtype={'p2010_zmaxn88ft': 'float64'},
            low_memory=False,
            nrows=None,  # Load all
        )
    except Exception as e:
        print(f"  ⚠️  Error reading CSV: {e}")
        return None
    
    print(f"  ✓ Loaded {len(df)} buildings")
    
    # Parse WKT geometry
    print("  📐 Parsing geometries...")
    try:
        df['geometry'] = df['shape'].apply(wkt.loads)
    except Exception as e:
        print(f"  ⚠️  Error parsing geometries: {e}")
        return None
    
    # Convert to GeoDataFrame
    try:
        gdf = gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:4326')
    except NameError:
        print(f"  ⚠️  geopandas not available")
        return None
    
    # Convert height from feet to meters (NAVD88 datum to absolute meters)
    # p2010_zmaxn88ft is relative to NAVD88, add mean offset for SF (~0m to sea level)
    gdf['height_m'] = gdf['p2010_zmaxn88ft'] * 0.3048  # feet to meters
    
    # Filter valid heights (remove nulls and unrealistic values)
    gdf = gdf[gdf['height_m'].notna()]
    gdf = gdf[(gdf['height_m'] > 2.0) & (gdf['height_m'] < 500.0)]  # 2m–500m
    
    print(f"  ✓ Valid buildings: {len(gdf)} (height range: {gdf['height_m'].min():.1f}–{gdf['height_m'].max():.1f}m)")
    
    # Clip to bounds if provided
    if bounds:
        min_lon, min_lat, max_lon, max_lat = bounds
        gdf = gdf.cx[min_lon:max_lon, min_lat:max_lat]
        print(f"  ✓ Clipped to bounds: {len(gdf)} buildings in region")
    
    return gdf[['height_m', 'geometry']]


# Global cache for buildings GeoDataFrame
_BUILDINGS_CACHE = None


def get_buildings_gdf(
    csv_path: str = "Building_Footprints_20260410.csv",
    bounds: tuple = None,
):
    """
    Get buildings GeoDataFrame (cached after first load).
    
    Parameters
    ----------
    csv_path : str
    bounds : tuple
        (min_lon, min_lat, max_lon, max_lat)
    
    Returns
    -------
    GeoDataFrame or None if dependencies missing
    """
    global _BUILDINGS_CACHE
    
    if _BUILDINGS_CACHE is None:
        _BUILDINGS_CACHE = load_buildings_gdf(csv_path, bounds)
    
    return _BUILDINGS_CACHE


def get_max_obstacle_height(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    buildings_gdf,
    buffer_m: float = 50.0,
) -> Optional[float]:
    """
    Find the maximum building height that intersects a corridor.
    
    Parameters
    ----------
    origin_lat, origin_lon : float
        Starting hub (degrees)
    dest_lat, dest_lon : float
        Destination hub (degrees)
    buildings_gdf : GeoDataFrame or None
        Loaded buildings with height_m column (or None)
    buffer_m : float
        Additional safety buffer above max building (meters)
    
    Returns
    -------
    float or None
        Obstacle height in meters (max building + buffer).
        None if no buildings intersect the corridor or dependencies missing.
    
    Example
    -------
    >>> h = get_max_obstacle_height(37.765, -122.431, 37.751, -122.414, buildings)
    >>> print(h)
    67.5  # meters (including 50m safety buffer)
    """
    
    if not HAS_GEO_DEPS:
        return None
    
    if buildings_gdf is None or len(buildings_gdf) == 0:
        return None
    
    # Create flight corridor as line
    flight_line = LineString([(origin_lon, origin_lat), (dest_lon, dest_lat)])
    
    try:
        # Find intersecting buildings
        intersecting = buildings_gdf[buildings_gdf.geometry.intersects(flight_line)]
        
        if len(intersecting) == 0:
            return None
        
        # Max height in corridor + buffer
        max_height = intersecting['height_m'].max()
        return max_height + buffer_m
    
    except Exception as e:
        print(f"  ⚠️  Error finding obstacles: {e}")
        return None


def add_obstacles_to_corridors(
    corridors: List,
    buildings_gdf,
) -> None:
    """
    Wire real obstacle heights into all corridors (mutates in place).
    
    Parameters
    ----------
    corridors : list of Corridor
    buildings_gdf : GeoDataFrame or None
        Buildings with height_m column
    """
    print(f"\n  🏢 Wiring obstacle heights ({len(corridors)} corridors)...")
    
    if buildings_gdf is None or len(buildings_gdf) == 0:
        print("  ⚠️  Buildings GeoDataFrame is empty, using fallback heights")
        return
    
    updated = 0
    for corridor in corridors:
        height = get_max_obstacle_height(
            origin_lat=corridor.origin.lat,
            origin_lon=corridor.origin.lon,
            dest_lat=corridor.destination.lat,
            dest_lon=corridor.destination.lon,
            buildings_gdf=buildings_gdf,
            buffer_m=50.0,  # 50m safety buffer
        )
        
        if height is not None:
            corridor.obstacle_height_m = height
            updated += 1
    
    print(f"  ✓ Updated {updated} corridors with real obstacle heights")
