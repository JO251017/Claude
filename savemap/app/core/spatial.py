from math import asin, cos, radians, sin, sqrt

import h3

WGS84_SRID = 4326
DEFAULT_H3_RES = 9
EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def to_h3(lat: float, lng: float, resolution: int = DEFAULT_H3_RES) -> int:
    return int(h3.latlng_to_cell(lat, lng, resolution), 16)


def h3_ring_cells(lat: float, lng: float, k: int, resolution: int = DEFAULT_H3_RES) -> list[str]:
    origin = h3.latlng_to_cell(lat, lng, resolution)
    return list(h3.grid_disk(origin, k))


def ewkt_point(lat: float, lng: float) -> str:
    return f"SRID={WGS84_SRID};POINT({lng} {lat})"
