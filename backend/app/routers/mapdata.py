"""Dữ liệu cho trang Bản đồ."""
from fastapi import APIRouter, Depends

from .. import db
from ..security import current_user
from ..services import overview, scoring
from ..services.features import SURVEY_RESULT_LABELS, DataSnapshot

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("")
def map_data(species: str = "aedes", days: int = 7, user: dict = Depends(current_user)):
    snapshot = DataSnapshot()
    end = snapshot.latest_weather_date()
    if not end:
        return {"has_data": False, "areas": [], "water_points": [], "surveys": []}
    start, _ = overview.window_ending(end, days)
    snaps = overview.area_snapshots(snapshot, end, species, start=start)
    areas = [{**overview.slim(s), "polygon": s["polygon"], "centroid": s["centroid"],
              "sources": scoring.collect_sources(s["components"])} for s in snaps]
    water = db.query("SELECT * FROM water_points WHERE observed_date<=? ORDER BY code", (end,))
    surveys = db.query("SELECT * FROM surveys WHERE survey_date<=? AND species=? ORDER BY code", (end, species))
    for s in surveys:
        s["result_label"] = SURVEY_RESULT_LABELS.get(s["result"], s["result"])
    return {"has_data": True, "period": {"start": start, "end": end}, "species": species,
            "scoring_version": scoring.SCORING_VERSION, "areas": areas, "water_points": water, "surveys": surveys}
