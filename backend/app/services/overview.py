"""Tổng hợp số liệu cho Dashboard, Bản đồ và Báo cáo (tính trực tiếp từ dữ liệu bằng scoring service)."""
from __future__ import annotations

from datetime import timedelta

from . import analysis, geo, scoring
from .features import DataSnapshot, parse_date

SCORING_WINDOW_DAYS = 7


def window_ending(end: str, days: int = SCORING_WINDOW_DAYS) -> tuple[str, str]:
    d1 = parse_date(end)
    return (d1 - timedelta(days=days - 1)).isoformat(), end


def area_snapshots(snapshot: DataSnapshot, end: str, species: str = "aedes", area_ids: list[int] | None = None,
                   start: str | None = None) -> list[dict]:
    start = start or window_ending(end)[0]
    out = []
    for area in geo.load_areas():
        if area_ids and area["id"] not in area_ids:
            continue
        result = analysis.evaluate(snapshot, area["id"], start, end, species)
        result.update(area_code=area["code"], area_name=area["name"], polygon=area["polygon"],
                      centroid=[area["centroid_lat"], area["centroid_lng"]])
        out.append(result)
    return out


def trend(snapshot: DataSnapshot, end: str, days: int, species: str = "aedes", area_ids: list[int] | None = None) -> list[dict]:
    """ESS/PIS trung bình theo ngày; mỗi ngày dùng cửa sổ 7 ngày kết thúc tại ngày đó."""
    areas = [a for a in geo.load_areas() if not area_ids or a["id"] in area_ids]
    earliest = snapshot.earliest_weather_date()
    points = []
    d1 = parse_date(end)
    for offset in range(days - 1, -1, -1):
        day = d1 - timedelta(days=offset)
        w_start, w_end = window_ending(day.isoformat())
        if earliest and w_start < earliest:
            continue  # chưa đủ 7 ngày dữ liệu trước đó → không vẽ điểm (không nội suy)
        ess_values, pis_values = [], []
        for area in areas:
            result = analysis.evaluate(snapshot, area["id"], w_start, w_end, species)
            if result["ess"] is not None:
                ess_values.append(result["ess"])
            if result["pis"] is not None:
                pis_values.append(result["pis"])
        points.append({
            "date": day.isoformat(),
            "ess": round(sum(ess_values) / len(ess_values), 1) if ess_values else None,
            "pis": round(sum(pis_values) / len(pis_values), 1) if pis_values else None,
            "areas_scored": len(ess_values),
        })
    return points


def distribution(snapshots: list[dict]) -> list[dict]:
    counts = {c["key"]: 0 for c in scoring.public_config()["ess_classes"]}
    not_scored = 0
    for snap in snapshots:
        if snap["ess_class"]:
            counts[snap["ess_class"]["key"]] += 1
        else:
            not_scored += 1
    out = [{"key": c["key"], "label": c["label"], "count": counts[c["key"]], "range": f"{c['min']:g}–{c['max']:g}"}
           for c in scoring.public_config()["ess_classes"]]
    out.append({"key": "not_scored", "label": "Không đủ dữ liệu", "count": not_scored, "range": "—"})
    return out


def slim(snap: dict) -> dict:
    keys = ("area_id", "area_code", "area_name", "status", "ess", "ess_class", "pis", "pis_class", "completeness",
            "missing", "features", "change_score", "start_date", "end_date", "scoring_version", "message")
    return {k: snap.get(k) for k in keys}
