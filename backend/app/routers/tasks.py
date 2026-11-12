"""AI Agent Center: tạo, theo dõi, hủy, thử lại nhiệm vụ."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..agents import orchestrator
from ..security import current_user, require

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    objective: str
    area_ids: list[int]
    start: str
    end: str
    species: str = "aedes"
    sources: list[str] = ["weather", "water", "survey"]
    notes: str | None = None
    simulate_fault: str = "none"


class CancelBody(BaseModel):
    reason: str | None = None


@router.post("")
def create(body: TaskBody, user: dict = Depends(require("task.create"))):
    task = orchestrator.create_task(body.objective, body.model_dump(exclude={"objective"}), user)
    orchestrator.start_task(task["id"])
    return task


@router.get("")
def list_tasks(user: dict = Depends(current_user)):
    return orchestrator.list_tasks()


@router.get("/{task_id}")
def detail(task_id: str, user: dict = Depends(current_user)):
    return orchestrator.get_task(task_id)


@router.post("/{task_id}/cancel")
def cancel(task_id: str, body: CancelBody, user: dict = Depends(require("task.create"))):
    return orchestrator.cancel_task(task_id, user, body.reason)


@router.post("/{task_id}/retry")
def retry(task_id: str, user: dict = Depends(require("task.create"))):
    return orchestrator.retry_task(task_id)
