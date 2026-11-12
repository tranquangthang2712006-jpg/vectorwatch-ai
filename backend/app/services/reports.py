"""Dựng nội dung báo cáo (xem trước) và xuất Excel. PDF được tạo bằng chức năng In → Lưu PDF của trình duyệt."""
from __future__ import annotations

import io

from .. import config, db
from . import alerts as alert_service
from . import overview, scoring
from .features import SURVEY_RESULT_LABELS, DataSnapshot

LIMITATIONS = [
    "Toàn bộ dữ liệu trong bản demo là dữ liệu mẫu giả lập; các ô khu vực không trùng ranh giới hành chính thật.",
    "ESS/PIS là điểm theo quy tắc của hệ thống về mức thuận lợi của điều kiện môi trường; không phải xác suất có véc-tơ, xác suất mắc bệnh hay dự báo dịch.",
    "Trọng số, đường cong và ngưỡng scoring là cấu hình minh họa, chưa được chuyên gia xác nhận.",
    "Điểm cao không khẳng định có muỗi hoặc ổ bọ gậy; mọi đề xuất cần xác minh thực địa và do con người phê duyệt.",
    "Dữ liệu thiếu không được coi là 0; khi thiếu, trọng số được chia lại hoặc không tính điểm.",
    "Bản ghi “chưa khảo sát” không được dùng làm bằng chứng không có véc-tơ.",
]


def build_report(area_ids: list[int] | None, start: str, end: str, species: str, user_name: str) -> dict:
    snapshot = DataSnapshot()
    snaps = overview.area_snapshots(snapshot, end, species, area_ids, start)
    scored = [s for s in snaps if s["ess"] is not None]
    ranked = sorted(scored, key=lambda s: s["pis"] if s["pis"] is not None else -1, reverse=True)
    ids = {s["area_id"] for s in snaps}
    all_alerts = [a for a in alert_service.list_alerts() if a["area_id"] in ids]
    approved = [a for a in all_alerts if a["status"] == "approved"]
    pending = [a for a in all_alerts if a["status"] in ("pending", "needs_revision")]
    last_task = db.query_one("SELECT id, trace_id, status, created_at FROM tasks WHERE is_test=0 ORDER BY created_at DESC LIMIT 1")

    vn = lambda iso: "/".join(reversed(iso.split("-")))  # noqa: E731 — YYYY-MM-DD → DD/MM/YYYY
    summary = [f"Kỳ báo cáo {vn(start)} → {vn(end)}, loài {scoring.SPECIES_REGISTRY[species]['label']}, {len(snaps)} khu vực."]
    if scored:
        mean_ess = sum(s["ess"] for s in scored) / len(scored)
        summary.append(f"ESS trung bình {mean_ess:.1f}/100 trên {len(scored)} khu vực tính được điểm.")
        high = [s for s in scored if s["pis"] is not None and s["pis"] >= 75]
        mid = [s for s in scored if s["pis"] is not None and 50 <= s["pis"] < 75]
        summary.append(f"{len(high)} khu vực ở mức “Ưu tiên kiểm tra” (PIS ≥ 75), {len(mid)} khu vực “Cần kiểm tra” (PIS 50–74).")
        if ranked:
            summary.append("PIS cao nhất: " + ", ".join(f"{s['area_name']} ({s['pis']:g})" for s in ranked[:3] if s["pis"] is not None) + ".")
    if len(scored) < len(snaps):
        summary.append(f"{len(snaps) - len(scored)} khu vực không đủ dữ liệu để tính ESS.")
    partial = [s for s in snaps if s["missing"]]
    if partial:
        summary.append(f"{len(partial)} khu vực thiếu một phần dữ liệu đầu vào (xem bảng).")
    summary.append(f"Đề xuất: {len(approved)} đã phê duyệt, {len(pending)} đang chờ quyết định.")

    recommendations = [{"code": a["code"], "area": a["area_name"], "action": a["recommended_action"], "status": "Đã phê duyệt",
                        "assignee": a["assignee"]} for a in approved]
    recommendations += [{"code": a["code"], "area": a["area_name"], "action": a["recommended_action"],
                         "status": a["status_label"] + " — chưa có hiệu lực", "assignee": a["assignee"]} for a in pending]

    sources = scoring.collect_sources([c for s in snaps for c in s["components"]])
    return {
        "title": "Báo cáo giám sát điều kiện môi trường thuận lợi cho véc-tơ",
        "generated_at": db.now_iso(),
        "generated_by": user_name,
        "period": {"start": start, "end": end},
        "species": scoring.SPECIES_REGISTRY[species]["label"],
        "scoring_version": scoring.SCORING_VERSION,
        "app_version": config.APP_VERSION,
        "data_label": "DỮ LIỆU MẪU / GIẢ LẬP",
        "summary": summary,
        "summary_generated_by": "Mẫu câu xác định từ số liệu đã tính (không dùng LLM)",
        "areas": [{
            "area_id": s["area_id"], "code": s["area_code"], "name": s["area_name"], "status": s["status"],
            "rainfall_7d": s["features"].get("rainfall_7d"), "temperature_mean": s["features"].get("temperature_mean"),
            "humidity_mean": s["features"].get("humidity_mean"), "water_points_active": s["features"].get("water_points_active"),
            "survey_positive_ratio": s["features"].get("survey_positive_ratio"),
            "survey_valid_count": s["features"].get("survey_valid_count"),
            "ess": s["ess"], "ess_class": s["ess_class"]["label"] if s["ess_class"] else None,
            "ess_class_key": s["ess_class"]["key"] if s["ess_class"] else None,
            "pis": s["pis"], "pis_class": s["pis_class"]["label"] if s["pis_class"] else None,
            "completeness": s["completeness"], "missing": [m["label"] for m in s["missing"]],
            "polygon": s["polygon"], "centroid": s["centroid"],
        } for s in snaps],
        "trend": overview.trend(snapshot, end, 14, species, area_ids),
        "distribution": overview.distribution(snaps),
        "alerts": [{k: a[k] for k in ("code", "area_name", "type_label", "severity_label", "status_label", "ess", "pis",
                                      "created_at", "recommended_action")} for a in all_alerts],
        "recommendations": recommendations,
        "limitations": LIMITATIONS,
        "sources": sources,
        "last_task": last_task,
        "has_data": bool(scored),
    }


def export_excel(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DCE6F1")

    def header(ws, columns):
        ws.append(columns)
        for cell in ws[ws.max_row]:
            cell.font = bold
            cell.fill = head_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws = wb.active
    ws.title = "Tóm tắt"
    ws.append([report["title"]]); ws["A1"].font = Font(bold=True, size=14)
    ws.append([report["data_label"]]); ws["A2"].font = Font(bold=True, color="C00000")
    ws.append(["Kỳ báo cáo", f"{report['period']['start']} → {report['period']['end']}"])
    ws.append(["Loài", report["species"]])
    ws.append(["Phiên bản scoring", report["scoring_version"]])
    ws.append(["Thời điểm tạo (UTC)", report["generated_at"]])
    ws.append(["Người tạo", report["generated_by"]])
    if report["last_task"]:
        ws.append(["Nhiệm vụ Agent gần nhất", report["last_task"]["id"]])
        ws.append(["trace_id", report["last_task"]["trace_id"]])
    ws.append([])
    ws.append(["Tóm tắt"]); ws.cell(ws.max_row, 1).font = bold
    for line in report["summary"]:
        ws.append([line])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 60

    ws = wb.create_sheet("Dữ liệu & kết quả")
    header(ws, ["Mã", "Khu vực", "Mưa quy đổi 7 ngày (mm)", "Nhiệt độ TB (°C)", "Độ ẩm TB (%)", "Điểm nước đọng đang tồn tại",
                "Tỷ lệ khảo sát dương tính", "Số lượt khảo sát hợp lệ", "ESS (0–100)", "Nhóm ESS", "PIS (0–100)", "Mức PIS",
                "Độ đầy đủ dữ liệu (%)", "Dữ liệu thiếu"])
    for a in report["areas"]:
        ws.append([a["code"], a["name"], a["rainfall_7d"], a["temperature_mean"], a["humidity_mean"], a["water_points_active"],
                   a["survey_positive_ratio"], a["survey_valid_count"], a["ess"], a["ess_class"] or "Không đủ dữ liệu",
                   a["pis"], a["pis_class"], round(a["completeness"] * 100), "; ".join(a["missing"]) or "Không"])
    for col in "ABCDEFGHIJKLMN":
        ws.column_dimensions[col].width = 18

    ws = wb.create_sheet("Xu hướng")
    header(ws, ["Ngày", "ESS trung bình", "PIS trung bình", "Số khu vực tính được"])
    for p in report["trend"]:
        ws.append([p["date"], p["ess"], p["pis"], p["areas_scored"]])

    ws = wb.create_sheet("Cảnh báo & khuyến nghị")
    header(ws, ["Mã", "Khu vực", "Loại", "Mức", "Trạng thái", "ESS", "PIS", "Thời điểm tạo (UTC)", "Hành động đề xuất"])
    for a in report["alerts"]:
        ws.append([a["code"], a["area_name"], a["type_label"], a["severity_label"], a["status_label"], a["ess"], a["pis"],
                   a["created_at"], a["recommended_action"]])
    for col in "ABCDEFGH":
        ws.column_dimensions[col].width = 20
    ws.column_dimensions["I"].width = 80

    ws = wb.create_sheet("Giới hạn & nguồn")
    header(ws, ["Giới hạn cần lưu ý"])
    for line in report["limitations"]:
        ws.append([line])
    ws.append([])
    header(ws, ["Nguồn dữ liệu"])
    for src in report["sources"] or ["(không có)"]:
        ws.append([src])
    ws.column_dimensions["A"].width = 120

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def survey_label(result: str) -> str:
    return SURVEY_RESULT_LABELS.get(result, result)
