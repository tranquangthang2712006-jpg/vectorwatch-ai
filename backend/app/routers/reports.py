"""Báo cáo (xem trước, xuất Excel) và bộ test case."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..security import current_user, require
from ..services import reports, scoring, testcases

router = APIRouter(prefix="/api", tags=["reports"])


def _build(area_id: int | None, start: str, end: str, species: str, user: dict) -> dict:
    spec = scoring.SPECIES_REGISTRY.get(species)
    if not spec or not spec.get("configured"):
        raise HTTPException(422, "Loài này chưa có bộ tham số trong MVP. Hãy chọn Aedes.")
    try:
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(422, "Ngày không hợp lệ. Dùng dạng YYYY-MM-DD.")
    if d0 > d1 or (d1 - d0).days + 1 > 31:
        raise HTTPException(422, "Khoảng thời gian không hợp lệ (tối đa 31 ngày, ngày bắt đầu ≤ ngày kết thúc).")
    return reports.build_report([area_id] if area_id else None, start, end, species, user["full_name"])


@router.get("/reports/preview")
def preview(start: str, end: str, area_id: int | None = None, species: str = "aedes", user: dict = Depends(current_user)):
    return _build(area_id, start, end, species, user)


@router.get("/reports/export.xlsx")
def export_xlsx(start: str, end: str, area_id: int | None = None, species: str = "aedes",
                user: dict = Depends(require("report.export"))):
    report = _build(area_id, start, end, species, user)
    if not report["has_data"]:
        raise HTTPException(400, "Không có khu vực nào tính được điểm trong kỳ này nên chưa thể xuất báo cáo. Hãy đổi khoảng thời gian hoặc bổ sung dữ liệu.")
    content = reports.export_excel(report)
    filename = f"vectorwatch_bao_cao_{start}_{end}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/tests")
def tests_latest(user: dict = Depends(current_user)):
    return testcases.latest()


@router.post("/tests/run")
def tests_run(user: dict = Depends(require("tests.run"))):
    return testcases.run_suite(user["full_name"])
