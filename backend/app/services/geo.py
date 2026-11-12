"""Tiện ích không gian đơn giản (không phụ thuộc thư viện GIS)."""
from __future__ import annotations

from .. import db

LAT_RANGE = (-90.0, 90.0)
LNG_RANGE = (-180.0, 180.0)


def point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    """Ray casting. polygon = [[lat, lng], ...]."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_cross:
                inside = not inside
        j = i
    return inside


def load_areas() -> list[dict]:
    areas = db.query("SELECT * FROM areas ORDER BY code")
    for area in areas:
        area["polygon"] = db.loads(area["polygon"], [])
    return areas


def find_area(lat: float, lng: float, areas: list[dict]) -> dict | None:
    for area in areas:
        if point_in_polygon(lat, lng, area["polygon"]):
            return area
    return None


def pilot_extent(areas: list[dict]) -> dict | None:
    points = [p for a in areas for p in a["polygon"]]
    if not points:
        return None
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    return {"min_lat": min(lats), "max_lat": max(lats), "min_lng": min(lngs), "max_lng": max(lngs)}
