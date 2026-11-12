"""Cảnh báo và phê duyệt."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..security import current_user, require
from ..services import alerts as alert_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class ManualBody(BaseModel):
    area_id: int
    note: str | None = None


class DecisionBody(BaseModel):
    action: str
    note: str | None = None


class ResubmitBody(BaseModel):
    recommended_action: str
    note: str | None = None


@router.get("")
def list_alerts(status: str | None = None, severity: str | None = None, area_id: int | None = None,
                since: str | None = None, user: dict = Depends(current_user)):
    return alert_service.list_alerts(status or None, severity or None, area_id, since or None)


@router.post("")
def create_manual(body: ManualBody, user: dict = Depends(require("alert.create"))):
    return alert_service.create_manual(body.area_id, body.note, user)


@router.get("/{alert_id}")
def detail(alert_id: int, user: dict = Depends(current_user)):
    return alert_service.get_alert(alert_id)


@router.post("/{alert_id}/decision")
def decide(alert_id: int, body: DecisionBody, user: dict = Depends(require("alert.approve"))):
    return alert_service.decide(alert_id, body.action, body.note, user)


@router.post("/{alert_id}/resubmit")
def resubmit(alert_id: int, body: ResubmitBody, user: dict = Depends(require("alert.create"))):
    return alert_service.resubmit(alert_id, body.recommended_action, body.note, user)
