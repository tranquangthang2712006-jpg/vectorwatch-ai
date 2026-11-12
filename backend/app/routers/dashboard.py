"""Số liệu trang Tổng quan."""
from fastapi import APIRouter, Depends, Query

from ..agents import orchestrator
from ..security import current_user
from ..services import alerts as alert_service
from ..services import overview, scoring
from ..services.features import DataSnapshot

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(area_id: int | None = None, days: int = Query(7, ge=7, le=30), species: str = "aedes",
              user: dict = Depends(current_user)):
    snapshot = DataSnapshot()
    end = snapshot.latest_weather_date()
    if not end:
        return {"has_data": False}
    area_ids = [area_id] if area_id else None
    snaps = overview.area_snapshots(snapshot, end, species, area_ids)
    scored = [s for s in snaps if s["ess"] is not None]
    alerts = alert_service.list_alerts(area_id=area_id)
    start, _ = overview.window_ending(end)
    return {
        "has_data": True,
        "period": {"start": start, "end": end, "trend_days": days},
        "scoring_version": scoring.SCORING_VERSION,
        "kpis": {
            "areas_monitored": len(snaps),
            "pending_alerts": sum(1 for a in alerts if a["status"] == "pending"),
            "areas_to_inspect": sum(1 for s in scored if s["pis"] is not None and s["pis"] >= 50),
            "mean_ess": round(sum(s["ess"] for s in scored) / len(scored), 1) if scored else None,
            "areas_scored": len(scored),
            "areas_partial": sum(1 for s in snaps if s["missing"]),
        },
        "trend": overview.trend(snapshot, end, days, species, area_ids),
        "distribution": overview.distribution(snaps),
        "areas": sorted((overview.slim(s) for s in snaps), key=lambda s: s["pis"] if s["pis"] is not None else -1, reverse=True),
        "recent_alerts": alerts[:6],
        "recent_tasks": [{k: t[k] for k in ("id", "objective", "status", "status_label", "created_at", "created_by", "current_step_label")}
                         for t in orchestrator.list_tasks(6)],
    }
