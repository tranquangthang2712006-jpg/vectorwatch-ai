"""Thông tin chung: khu vực, cấu hình scoring (chỉ đọc), trạng thái hệ thống."""
from fastapi import APIRouter, Depends

from .. import config, db
from ..agents import llm as llm_layer
from ..agents.llm import WORKFLOW_PLAN
from ..agents.tools import MAX_RETRIES, TOOLS, tool_catalog
from ..security import PERMISSION_LABELS, PERMISSIONS, ROLES, current_user
from ..services import geo, scoring
from ..services.features import SURVEY_RESULT_LABELS, DataSnapshot

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok", "app": config.APP_NAME, "version": config.APP_VERSION}


@router.get("/meta")
def meta(user: dict = Depends(current_user)):
    snapshot = DataSnapshot()
    areas = geo.load_areas()
    counts = {t: db.query_one(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in ("weather", "water_points", "surveys")}
    return {
        "app": {"name": config.APP_NAME, "version": config.APP_VERSION},
        "areas": [{"id": a["id"], "code": a["code"], "name": a["name"], "centroid": [a["centroid_lat"], a["centroid_lng"]],
                   "is_synthetic": bool(a["is_synthetic"])} for a in areas],
        "extent": geo.pilot_extent(areas),
        "data": {"latest_date": snapshot.latest_weather_date(), "earliest_date": snapshot.earliest_weather_date(),
                 "counts": counts, "label": "Dữ liệu mẫu / giả lập"},
        "species": [{"key": k, "label": v["label"], "configured": v.get("configured", False)}
                    for k, v in scoring.SPECIES_REGISTRY.items()],
        "scoring": scoring.public_config(),
        "survey_result_labels": SURVEY_RESULT_LABELS,
        "agent": {**llm_layer.status(), "workflow": WORKFLOW_PLAN, "tools": sorted(TOOLS), "tool_policy": tool_catalog(),
                  "chat_intents": [{"key": k, **v} for k, v in llm_layer.CHAT_INTENTS.items()], "max_tool_retries": MAX_RETRIES},
        "roles": [{"key": k, "label": v, "permissions": [PERMISSION_LABELS[p] for p in sorted(PERMISSIONS[k])]}
                  for k, v in ROLES.items()],
    }
