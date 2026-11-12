"""Chạy và tra cứu phân tích điều kiện môi trường."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..security import current_user, require
from ..services import analysis, geo, scoring

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunBody(BaseModel):
    area_id: int
    species: str = "aedes"
    start: str
    end: str


@router.post("/run")
def run(body: RunBody, user: dict = Depends(require("analysis.run"))):
    spec = scoring.SPECIES_REGISTRY.get(body.species)
    if not spec or not spec.get("configured"):
        raise HTTPException(422, "Loài này chưa có bộ tham số trong MVP. Hãy chọn Aedes.")
    if body.area_id not in {a["id"] for a in geo.load_areas()}:
        raise HTTPException(404, "Không tìm thấy khu vực. Hãy chọn lại.")
    try:
        start, end = date.fromisoformat(body.start), date.fromisoformat(body.end)
    except ValueError:
        raise HTTPException(422, "Ngày không hợp lệ. Dùng dạng YYYY-MM-DD.")
    if start > end:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    if (end - start).days + 1 > 31:
        raise HTTPException(422, "Khoảng thời gian tối đa 31 ngày cho một lần phân tích.")
    return analysis.run_and_save(body.area_id, body.start, body.end, body.species, user["full_name"])


@router.get("/runs")
def runs(area_id: int | None = None, limit: int = 30, user: dict = Depends(current_user)):
    sql = """SELECT r.id, r.area_id, a.code AS area_code, a.name AS area_name, r.species, r.start_date, r.end_date, r.status,
                    r.ess, r.ess_class, r.pis, r.pis_class, r.completeness, r.scoring_version, r.created_at, r.created_by, r.task_id
             FROM analysis_runs r JOIN areas a ON a.id = r.area_id
             LEFT JOIN tasks t ON t.id = r.task_id WHERE COALESCE(t.is_test, 0) = 0"""
    params: list = []
    if area_id:
        sql += " AND r.area_id=?"
        params.append(area_id)
    sql += " ORDER BY r.id DESC LIMIT ?"
    params.append(min(limit, 200))
    return db.query(sql, params)


@router.get("/runs/{run_id}")
def run_detail(run_id: int, user: dict = Depends(current_user)):
    result = analysis.get_run(run_id)
    if not result:
        raise HTTPException(404, "Không tìm thấy lần phân tích này.")
    return result
