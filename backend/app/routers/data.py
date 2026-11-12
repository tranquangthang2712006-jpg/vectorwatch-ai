"""Quản lý dữ liệu: xem, nhập form/CSV/Excel có xem trước, lịch sử nhập."""
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import db
from ..security import current_user, require
from ..services import validation
from ..services.features import SURVEY_RESULT_LABELS

router = APIRouter(prefix="/api/data", tags=["data"])

TABLES = {
    "weather": ("""SELECT w.id, a.code AS area_code, a.name AS area_name, w.obs_date AS date, w.rainfall_mm, w.temperature_c,
                          w.humidity_pct, w.source, w.batch_id FROM weather w JOIN areas a ON a.id=w.area_id""",
                "w.area_id", "w.obs_date", "w.obs_date DESC, a.code"),
    "water": ("""SELECT p.id, p.code, a.code AS area_code, p.latitude, p.longitude, p.water_type, p.status, p.persistence_days,
                        p.observed_date, p.notes, p.source, p.batch_id FROM water_points p JOIN areas a ON a.id=p.area_id""",
              "p.area_id", "p.observed_date", "p.observed_date DESC, p.code"),
    "survey": ("""SELECT s.id, s.code, a.code AS area_code, s.latitude, s.longitude, s.survey_date, s.species, s.result,
                         s.vector_count, s.notes, s.entered_by, s.source, s.batch_id FROM surveys s JOIN areas a ON a.id=s.area_id""",
               "s.area_id", "s.survey_date", "s.survey_date DESC, s.code"),
}


def _kind(kind: str) -> str:
    if kind not in TABLES:
        raise HTTPException(404, "Loại dữ liệu không tồn tại. Chọn thời tiết, khảo sát hoặc điểm nước đọng.")
    return kind


@router.get("/{kind}")
def list_rows(kind: str, area_id: int | None = None, since: str | None = None, page: int = 1, page_size: int = 25,
              user: dict = Depends(current_user)):
    base, area_col, date_col, order = TABLES[_kind(kind)]
    where, params = [], []
    if area_id:
        where.append(f"{area_col}=?"); params.append(area_id)
    if since:
        where.append(f"{date_col}>=?"); params.append(since)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.query_one(f"SELECT COUNT(*) AS n FROM ({base}{clause})", params)["n"]
    page_size = max(5, min(page_size, 100))
    rows = db.query(f"{base}{clause} ORDER BY {order} LIMIT ? OFFSET ?", (*params, page_size, (max(page, 1) - 1) * page_size))
    if kind == "survey":
        for r in rows:
            r["result_label"] = SURVEY_RESULT_LABELS.get(r["result"], r["result"])
    return {"rows": rows, "total": total, "page": page, "page_size": page_size, "columns": validation.KINDS[kind]["columns"]}


@router.get("/{kind}/template.csv", response_class=PlainTextResponse)
def template(kind: str, user: dict = Depends(current_user)):
    return PlainTextResponse(validation.template_csv(_kind(kind)), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="mau_{kind}.csv"'})


class RowsBody(BaseModel):
    rows: list[dict]
    filename: str | None = None
    duplicate_policy: str = "skip"
    confirm_overwrite: bool = False


@router.post("/{kind}/preview")
async def preview(kind: str, file: UploadFile | None = File(default=None), rows: str | None = Form(default=None),
                  user: dict = Depends(require("data.write"))):
    _kind(kind)
    filename = None
    try:
        if file is not None:
            filename = file.filename
            content = await file.read()
            if len(content) > 2_000_000:
                raise ValueError("Tệp lớn hơn 2 MB. Hãy chia nhỏ tệp.")
            raw_rows = validation.parse_upload(filename or "", content, kind)
        elif rows:
            raw_rows = json.loads(rows)
        else:
            raise ValueError("Chưa có dữ liệu. Hãy chọn tệp hoặc điền biểu mẫu.")
    except json.JSONDecodeError:
        raise HTTPException(400, "Dữ liệu biểu mẫu không đọc được. Hãy tải lại trang và thử lại.")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        raise HTTPException(400, "Không đọc được tệp. Hãy kiểm tra tệp có đúng định dạng .csv (UTF-8) hoặc .xlsx và thử lại.")
    if not raw_rows:
        raise HTTPException(400, "Tệp không có dòng dữ liệu nào (chỉ có tiêu đề hoặc rỗng).")
    report = validation.validate_rows(kind, raw_rows)
    report["filename"] = filename
    return report


@router.post("/{kind}/commit")
def commit(kind: str, body: RowsBody, user: dict = Depends(require("data.write"))):
    _kind(kind)
    if body.duplicate_policy == "overwrite" and not body.confirm_overwrite:
        raise HTTPException(409, "Cần xác nhận rõ ràng trước khi ghi đè bản ghi đã có. Hãy tích ô xác nhận ghi đè.")
    if not body.rows:
        raise HTTPException(400, "Không có dòng nào để lưu.")
    try:
        return validation.commit_rows(kind, body.rows, user["full_name"], body.filename, body.duplicate_policy)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/batches/history")
def batches(user: dict = Depends(current_user)):
    return db.query("SELECT * FROM import_batches ORDER BY created_at DESC LIMIT 50")
