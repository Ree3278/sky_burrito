"""
Hard-coded hub registry for the 12 candidate Launch Hubs.

Source: K-Means output from siting_strategy.clustering (k=12, fit on 927
active food businesses in the Mission–Noe corridor, April 2026).

Each hub carries:
  - lat, lon          : cluster center coordinates (EPSG:4326)
  - restaurants_nearby: count within 420-m (5-min) walk zone
  - resunits_nearby   : residential units within 420-m walk zone
  - match_score       : restaurants × resunits (raw supply–demand overlap)

Replace with siting_strategy.fit_hubs() output once the pipeline is integrated.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Hub:
    id: int
    lat: float
    lon: float
    restaurants_nearby: int
    resunits_nearby: int

    @property
    def match_score(self) -> int:
        return self.restaurants_nearby * self.resunits_nearby

    @property
    def coords(self):
        """(lon, lat) tuple — matches GeoDataFrame / Shapely convention."""
        return (self.lon, self.lat)

    def __repr__(self):
        return (
            f"Hub {self.id} ({self.lat:.6f}, {self.lon:.6f}) | "
            f"{self.restaurants_nearby} restaurants | "
            f"{self.resunits_nearby:,} units"
        )


HUBS: List[Hub] = [
    Hub(id=1,  lat=37.765234, lon=-122.430998, restaurants_nearby=83,  resunits_nearby=3318),
    Hub(id=2,  lat=37.751203, lon=-122.414343, restaurants_nearby=89,  resunits_nearby=2858),
    Hub(id=3,  lat=37.764043, lon=-122.416897, restaurants_nearby=94,  resunits_nearby=2832),
    Hub(id=4,  lat=37.751370, lon=-122.429386, restaurants_nearby=52,  resunits_nearby=2404),
    Hub(id=5,  lat=37.764694, lon=-122.422360, restaurants_nearby=136, resunits_nearby=4944),
    Hub(id=6,  lat=37.751569, lon=-122.436101, restaurants_nearby=34,  resunits_nearby=2002),
    Hub(id=7,  lat=37.751260, lon=-122.419122, restaurants_nearby=101, resunits_nearby=3191),
    Hub(id=8,  lat=37.760493, lon=-122.419805, restaurants_nearby=160, resunits_nearby=4117),
    Hub(id=9,  lat=37.753501, lon=-122.410158, restaurants_nearby=51,  resunits_nearby=2138),
    Hub(id=10, lat=37.761275, lon=-122.411260, restaurants_nearby=55,  resunits_nearby=1621),
    Hub(id=11, lat=37.761320, lon=-122.435603, restaurants_nearby=91,  resunits_nearby=2763),
    Hub(id=12, lat=37.755812, lon=-122.420017, restaurants_nearby=145, resunits_nearby=3610),
]

HUB_LOOKUP = {h.id: h for h in HUBS}
