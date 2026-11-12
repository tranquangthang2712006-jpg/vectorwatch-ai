"""Cảnh báo / đề xuất kiểm tra và quy trình phê duyệt của con người (human-in-the-loop).

Agent chỉ TẠO ĐỀ XUẤT ở trạng thái chờ duyệt. Không có hành động nào được phát ra ngoài hệ thống.
"""
from __future__ import annotations

from fastapi import HTTPException

from .. import db
from . import analysis, geo, scoring
from .features import DataSnapshot

STATUS_LABELS = {"pending": "Chờ phê duyệt", "approved": "Đã phê duyệt", "rejected": "Đã từ chối",
                 "needs_revision": "Yêu cầu chỉnh sửa"}
SEVERITY_LABELS = {"high": "Cao", "medium": "Trung bình", "low": "Thấp", "info": "Thông tin"}
TYPE_LABELS = {
    "priority_inspection": "Ưu tiên kiểm tra thực địa",
    "inspection_needed": "Cần kiểm tra",
    "missing_data": "Thiếu / cần xác minh dữ liệu",
    "manual_request": "Yêu cầu kiểm tra (tạo thủ công)",
}
OPEN_STATUSES = ("pending", "needs_revision")


def _reasons(result: dict) -> list[str]:
    reasons = []
    if result["ess"] is not None:
        reasons.append(f"ESS {result['ess']:g}/100 ({result['ess_class']['label']}), PIS "
                       + (f"{result['pis']:g}/100 ({result['pis_class']['label']})" if result["pis"] is not None else "không tính được") + ".")
        ranked = sorted((c for c in result["components"] if not c["missing"]), key=lambda c: c["contribution"], reverse=True)
        for comp in ranked[:3]:
            reasons.append(f"{comp['label']}: {comp['value']:g} {comp['unit']} → {comp['score']:g} điểm.")
        if result.get("change_score"):
            reasons.append(f"ESS tăng so với kỳ trước (ChangeScore {result['change_score']:g}).")
    else:
        reasons.append(result.get("message") or "Không đủ dữ liệu để tính ESS.")
    for m in result["missing"]:
        reasons.append(f"Thiếu dữ liệu — {m['label']}: {m['reason']}")
    return reasons


def _classify(result: dict) -> tuple[str, str, str] | None:
    """Quy tắc tạo đề xuất (minh họa). Trả về (loại, mức, hành động đề xuất) hoặc None."""
    if result["ess"] is None:
        return ("missing_data", "low",
                "Bổ sung/xác minh dữ liệu đầu vào còn thiếu trước khi đánh giá khu vực này.")
    pis = result["pis"]
    if pis is not None and pis >= 75:
        return ("priority_inspection", "high",
                "Ưu tiên kiểm tra thực địa: rà soát các điểm nước đọng đang tồn tại và xác minh có/không ổ bọ gậy.")
    if pis is not None and pis >= 50:
        return ("inspection_needed", "medium",
                "Lên lịch kiểm tra thực địa các điểm nước đọng; cập nhật kết quả khảo sát vào hệ thống.")
    if result["missing"]:
        return ("missing_data", "info",
                "Theo dõi bổ sung: thu thập phần dữ liệu còn thiếu để điểm đánh giá đáng tin cậy hơn.")
    return None


def _next_code() -> str:
    row = db.query_one("SELECT COUNT(*) AS n FROM alerts")
    return f"ALT-{row['n'] + 1:04d}"


def _add_history(alert_id: int, action: str, actor: str, role: str, note: str | None) -> None:
    db.execute("INSERT INTO alert_history (alert_id, action, actor, actor_role, note, created_at) VALUES (?,?,?,?,?,?)",
               (alert_id, action, actor, role, note, db.now_iso()))


def _upsert(result: dict, kind: tuple[str, str, str], origin: str, task_id: str | None, user_name: str,
            role: str, areas: dict, note: str | None = None) -> dict:
    alert_type, severity, action = kind
    area = areas[result["area_id"]]
    sources = scoring.collect_sources(result["components"])
    factors = [{k: c.get(k) for k in ("key", "label", "value", "unit", "score", "contribution", "missing")}
               for c in result["components"]]
    now = db.now_iso()
    existing = db.query_one(
        "SELECT * FROM alerts WHERE area_id=? AND alert_type=? AND status IN ('pending','needs_revision')",
        (area["id"], alert_type))
    if existing:
        db.execute("""UPDATE alerts SET severity=?, ess=?, pis=?, reasons=?, factors=?, sources=?, task_id=COALESCE(?, task_id),
                      run_id=?, status='pending', updated_at=? WHERE id=?""",
                   (severity, result["ess"], result["pis"], db.dumps(_reasons(result)), db.dumps(factors), db.dumps(sources),
                    task_id, result.get("run_id"), now, existing["id"]))
        _add_history(existing["id"], "updated", user_name, role,
                     "Cập nhật số liệu từ lần phân tích mới (gộp để tránh cảnh báo trùng).")
        if task_id and existing["task_id"] and existing["task_id"] != task_id:
            # Đề xuất được gộp sang nhiệm vụ mới → nhiệm vụ cũ không còn chờ đề xuất này.
            from ..agents import orchestrator
            orchestrator.refresh_after_decision(existing["task_id"])
        return {"id": existing["id"], "code": existing["code"], "is_new": False, "area_code": area["code"], "area_id": area["id"]}
    code = _next_code()
    alert_id = db.execute(
        """INSERT INTO alerts (code, area_id, alert_type, severity, status, ess, pis, reasons, factors, sources,
           recommended_action, assignee, origin, task_id, run_id, created_by, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, area["id"], alert_type, severity, "pending", result["ess"], result["pis"], db.dumps(_reasons(result)),
         db.dumps(factors), db.dumps(sources), action, f"Tổ giám sát môi trường — {area['name']} (dự kiến)", origin,
         task_id, result.get("run_id"), user_name, now, now))
    _add_history(alert_id, "created", user_name, role, note or "Đề xuất được tạo, chờ người có thẩm quyền duyệt.")
    return {"id": alert_id, "code": code, "is_new": True, "area_code": area["code"], "area_id": area["id"]}


def propose_from_results(results: list[dict], task_id: str, user_name: str) -> list[dict]:
    areas = {a["id"]: a for a in geo.load_areas()}
    created = []
    for result in results:
        kind = _classify(result)
        if kind:
            created.append(_upsert(result, kind, "agent", task_id, "Risk & Alert Agent", "agent", areas,
                                   f"Tạo bởi Risk & Alert Agent trong nhiệm vụ {task_id} (khởi tạo bởi {user_name})."))
    return created


def create_manual(area_id: int, note: str | None, user: dict) -> dict:
    areas = {a["id"]: a for a in geo.load_areas()}
    if area_id not in areas:
        raise HTTPException(404, "Không tìm thấy khu vực. Hãy chọn lại khu vực trên bản đồ.")
    snapshot = DataSnapshot()
    window = analysis.default_window(snapshot)
    if not window:
        raise HTTPException(400, "Chưa có dữ liệu thời tiết để phân tích. Hãy nhập dữ liệu ở trang Quản lý dữ liệu.")
    result = analysis.run_and_save(area_id, window[0], window[1], "aedes", user["full_name"], snapshot=snapshot)
    severity = "high" if (result["pis"] or 0) >= 75 else "medium" if (result["pis"] or 0) >= 50 else "low"
    kind = ("manual_request", severity, "Kiểm tra thực địa theo yêu cầu của người dùng; xác minh các điểm nước đọng đã ghi nhận.")
    created = _upsert(result, kind, "manual", None, user["full_name"], user["role"], areas,
                      f"Tạo thủ công từ bản đồ. Ghi chú: {note}" if note else "Tạo thủ công từ bản đồ.")
    return get_alert(created["id"]) | {"is_new": created["is_new"]}


def _hydrate(row: dict, areas: dict) -> dict:
    area = areas.get(row["area_id"], {})
    row.update(
        reasons=db.loads(row["reasons"], []), factors=db.loads(row["factors"], []), sources=db.loads(row["sources"], []),
        area_code=area.get("code"), area_name=area.get("name"),
        status_label=STATUS_LABELS.get(row["status"], row["status"]),
        severity_label=SEVERITY_LABELS.get(row["severity"], row["severity"]),
        type_label=TYPE_LABELS.get(row["alert_type"], row["alert_type"]),
    )
    return row


def list_alerts(status: str | None = None, severity: str | None = None, area_id: int | None = None,
                since: str | None = None, limit: int = 200) -> list[dict]:
    sql, params = "SELECT * FROM alerts WHERE 1=1", []
    if status:
        sql += " AND status=?"; params.append(status)
    if severity:
        sql += " AND severity=?"; params.append(severity)
    if area_id:
        sql += " AND area_id=?"; params.append(area_id)
    if since:
        sql += " AND created_at>=?"; params.append(since)
    sql += " ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'needs_revision' THEN 1 ELSE 2 END, updated_at DESC LIMIT ?"
    params.append(limit)
    areas = {a["id"]: a for a in geo.load_areas()}
    return [_hydrate(r, areas) for r in db.query(sql, params)]


def get_alert(alert_id: int) -> dict:
    row = db.query_one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy cảnh báo. Có thể danh sách đã thay đổi — hãy tải lại trang.")
    areas = {a["id"]: a for a in geo.load_areas()}
    alert = _hydrate(row, areas)
    alert["history"] = db.query("SELECT * FROM alert_history WHERE alert_id=? ORDER BY id", (alert_id,))
    return alert


DECISIONS = {"approve": ("approved", "approved"), "reject": ("rejected", "rejected"),
             "request_revision": ("needs_revision", "revision_requested")}


def decide(alert_id: int, action: str, note: str | None, user: dict) -> dict:
    if action not in DECISIONS:
        raise HTTPException(400, "Quyết định không hợp lệ. Chọn Phê duyệt, Từ chối hoặc Yêu cầu chỉnh sửa.")
    note = (note or "").strip()
    if action in ("reject", "request_revision") and len(note) < 5:
        raise HTTPException(422, "Cần nhập ghi chú (ít nhất 5 ký tự) khi từ chối hoặc yêu cầu chỉnh sửa.")
    alert = get_alert(alert_id)
    if alert["status"] != "pending":
        raise HTTPException(409, f"Cảnh báo đang ở trạng thái “{alert['status_label']}” nên không thể ra quyết định. "
                                 "Nếu đang chờ chỉnh sửa, người tạo cần cập nhật và gửi lại trước.")
    new_status, history_action = DECISIONS[action]
    db.execute("UPDATE alerts SET status=?, updated_at=? WHERE id=?", (new_status, db.now_iso(), alert_id))
    _add_history(alert_id, history_action, user["full_name"], user["role"], note or None)
    if alert["task_id"]:
        from ..agents import orchestrator  # nhập trễ để tránh vòng lặp import

        orchestrator.refresh_after_decision(alert["task_id"])
    return get_alert(alert_id)


def resubmit(alert_id: int, recommended_action: str, note: str | None, user: dict) -> dict:
    alert = get_alert(alert_id)
    if alert["status"] != "needs_revision":
        raise HTTPException(409, "Chỉ gửi lại được đề xuất đang ở trạng thái “Yêu cầu chỉnh sửa”.")
    recommended_action = (recommended_action or "").strip()
    if len(recommended_action) < 10:
        raise HTTPException(422, "Nội dung đề xuất quá ngắn. Hãy mô tả hành động kiểm tra cụ thể (ít nhất 10 ký tự).")
    db.execute("UPDATE alerts SET recommended_action=?, status='pending', updated_at=? WHERE id=?",
               (recommended_action, db.now_iso(), alert_id))
    _add_history(alert_id, "resubmitted", user["full_name"], user["role"], (note or "").strip() or "Đã chỉnh sửa và gửi lại.")
    return get_alert(alert_id)
