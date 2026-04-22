"""Filesystem paths shared across the project."""

from pathlib import Path

DATA_DIR = Path("data")

RESTAURANTS_CSV = DATA_DIR / "Registered_Business_Locations_-_San_Francisco_20260410.csv"
BUILDINGS_CSV = DATA_DIR / "Building_Footprints_20260410.csv"
LANDUSE_CSV = DATA_DIR / "San_Francisco_Land_Use_-_2023_20260410.csv"

STREAMLIT_APP = Path("simulation/app.py")

