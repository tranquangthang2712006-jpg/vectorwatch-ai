"""Công cụ (tools) mà các Agent được phép gọi, và ToolRunner ghi log + retry có giới hạn.

Mọi công cụ là hàm Python thật thao tác trên CSDL / service; mỗi lần gọi (kể cả lần thất bại) đều được
ghi vào bảng tool_calls. Input được làm sạch trước khi lưu.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable

from .. import db
from ..services import alerts as alert_service
from ..services import analysis, geo
from ..services.features import DataSnapshot

MAX_RETRIES = 2  # tối đa 1 lần gọi + 2 lần thử lại
SENSITIVE_KEYS = ("password", "token", "secret", "api_key", "authorization")


class ToolError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class TaskCancelled(Exception):
    pass


def sanitize(value: Any, depth: int = 0) -> Any:
    """Loại khóa nhạy cảm, rút gọn danh sách/chuỗi dài để log gọn và an toàn."""
    if isinstance(value, dict):
        return {k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else sanitize(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [sanitize(v, depth + 1) for v in value[:12]]
        if len(value) > 12:
            items.append(f"… (+{len(value) - 12} phần tử)")
        return items
    if isinstance(value, str) and len(value) > 300:
        return value[:300] + "…"
    return value


# ---------------------------------------------------------------------------
# Các công cụ
# ---------------------------------------------------------------------------
def get_weather_data(area_ids: list[int], start: str, end: str) -> dict:
    marks = ",".join("?" * len(area_ids))
    rows = db.query(f"SELECT * FROM weather WHERE area_id IN ({marks}) AND obs_date BETWEEN ? AND ?", (*area_ids, start, end))
    return {"rows": rows, "summary": f"{len(rows)} bản ghi thời tiết cho {len(area_ids)} khu vực ({start} → {end})",
            "sources": sorted({r["source"] for r in rows})}


def get_water_points(area_ids: list[int], end: str) -> dict:
    marks = ",".join("?" * len(area_ids))
    rows = db.query(f"SELECT * FROM water_points WHERE area_id IN ({marks}) AND observed_date <= ?", (*area_ids, end))
    active = sum(1 for r in rows if r["status"] == "active")
    return {"rows": rows, "summary": f"{len(rows)} điểm nước đọng ({active} đang tồn tại)",
            "sources": sorted({r["source"] for r in rows})}


def get_survey_data(area_ids: list[int], end: str, species: str) -> dict:
    marks = ",".join("?" * len(area_ids))
    rows = db.query(f"SELECT * FROM surveys WHERE area_id IN ({marks}) AND survey_date <= ? AND species=?", (*area_ids, end, species))
    pending = sum(1 for r in rows if r["result"] == "not_surveyed")
    return {"rows": rows, "summary": f"{len(rows)} bản ghi khảo sát ({pending} ở trạng thái chưa khảo sát)",
            "sources": sorted({r["source"] for r in rows})}


def validate_dataset(area_ids: list[int], start: str, end: str, species: str, sources: list[str]) -> dict:
    snapshot = DataSnapshot()
    areas = {a["id"]: a for a in geo.load_areas()}
    issues, per_area = [], []
    for area_id in area_ids:
        feats = snapshot.features(area_id, start, end, species, tuple(sources))
        missing = [{"feature": k, "reason": v["missing_reason"]} for k, v in feats["_meta"].items() if "missing_reason" in v]
        per_area.append({"area_code": areas[area_id]["code"], "missing": missing})
        for m in missing:
            issues.append(f"{areas[area_id]['code']}: {m['reason']}")
    complete = sum(1 for a in per_area if not a["missing"])
    return {"per_area": per_area, "issues": issues,
            "summary": f"{complete}/{len(area_ids)} khu vực đủ dữ liệu; {len(issues)} mục thiếu được ghi nhận (không thay bằng 0)"}


def compute_environmental_score(area_id: int, start: str, end: str, species: str, sources: list[str],
                                task_id: str, user_name: str) -> dict:
    result = analysis.run_and_save(area_id, start, end, species, user_name, tuple(sources), task_id)
    slim = {k: result[k] for k in ("run_id", "area_id", "status", "ess", "ess_class", "pis", "pis_class", "completeness",
                                    "missing", "scoring_version", "components", "change_score", "message")}
    ess = "không tính được" if result["ess"] is None else f"{result['ess']:g}"
    pis = "—" if result["pis"] is None else f"{result['pis']:g}"
    slim["summary"] = f"ESS {ess}, PIS {pis}, độ đầy đủ {result['completeness'] * 100:.0f}% (scoring {result['scoring_version']})"
    return slim


def build_map_layer(results: list[dict], end: str) -> dict:
    areas = {a["id"]: a for a in geo.load_areas()}
    features, unmatched = [], 0
    for res in results:
        area = areas[res["area_id"]]
        points = db.query("SELECT latitude, longitude FROM water_points WHERE area_id=? AND status='active' AND observed_date<=?",
                          (area["id"], end))
        inside = sum(1 for p in points if geo.point_in_polygon(p["latitude"], p["longitude"], area["polygon"]))
        unmatched += len(points) - inside
        features.append({"area_id": area["id"], "area_code": area["code"], "centroid": [area["centroid_lat"], area["centroid_lng"]],
                         "ess": res["ess"], "pis": res["pis"], "active_water_points_in_polygon": inside})
    return {"features": features, "unmatched_points": unmatched,
            "summary": f"Đã gắn kết quả cho {len(features)} khu vực lên lớp bản đồ; {unmatched} điểm không khớp ranh giới"}


def rank_priority_locations(results: list[dict]) -> dict:
    areas = {a["id"]: a for a in geo.load_areas()}
    scored = [r for r in results if r["pis"] is not None]
    ranked = sorted(scored, key=lambda r: r["pis"], reverse=True)
    ranking = [{"rank": i + 1, "area_id": r["area_id"], "area_code": areas[r["area_id"]]["code"], "ess": r["ess"],
                "pis": r["pis"], "pis_class": r["pis_class"]["label"], "run_id": r["run_id"]} for i, r in enumerate(ranked)]
    not_scored = [areas[r["area_id"]]["code"] for r in results if r["pis"] is None]
    return {"ranking": ranking, "not_scored": not_scored,
            "summary": f"Xếp hạng {len(ranking)} khu vực theo PIS; {len(not_scored)} khu vực không đủ dữ liệu để xếp hạng"}


def create_alert_proposals(results: list[dict], task_id: str, user_name: str) -> dict:
    created = alert_service.propose_from_results(results, task_id, user_name)
    new = sum(1 for c in created if c["is_new"])
    return {"alerts": created,
            "summary": f"{new} đề xuất mới, {len(created) - new} đề xuất đang chờ được cập nhật (chống lặp); tất cả ở trạng thái chờ duyệt"}


# --- Công cụ CHỈ ĐỌC phục vụ Trợ lý hỏi đáp (không ghi CSDL) -------------------
def _area_map() -> dict:
    return {a["id"]: a for a in geo.load_areas()}


def get_environmental_score(area_ids: list[int], start: str, end: str, species: str) -> dict:
    """Tính ESS/PIS bằng scoring service nhưng KHÔNG lưu — dùng cho câu hỏi tra cứu."""
    snapshot, areas, results = DataSnapshot(), _area_map(), []
    for area_id in area_ids:
        r = analysis.evaluate(snapshot, area_id, start, end, species)
        results.append({"area_id": area_id, "area_code": areas[area_id]["code"], "status": r["status"], "ess": r["ess"],
                        "ess_class": r["ess_class"], "pis": r["pis"], "pis_class": r["pis_class"],
                        "completeness": r["completeness"], "missing": r["missing"], "components": r["components"],
                        "previous_period": r["previous_period"], "change_score": r["change_score"],
                        "explanation": r["explanation"], "scoring_version": r["scoring_version"],
                        "start_date": r["start_date"], "end_date": r["end_date"]})
    scored = sum(1 for r in results if r["ess"] is not None)
    return {"results": results, "summary": f"Tính ESS/PIS (không lưu) cho {len(results)} khu vực; {scored} khu vực đủ dữ liệu"}


def summarize_weather(area_ids: list[int], start: str, end: str) -> dict:
    """Tổng hợp thời tiết theo khu vực; ngày thiếu số liệu được đếm riêng, không coi là 0."""
    rows = get_weather_data(area_ids, start, end)["rows"]
    areas, per = _area_map(), []
    n_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    for area_id in area_ids:
        mine = [r for r in rows if r["area_id"] == area_id]
        def vals(col):
            return [r[col] for r in mine if r[col] is not None]
        rain, temp, hum = vals("rainfall_mm"), vals("temperature_c"), vals("humidity_pct")
        per.append({"area_id": area_id, "area_code": areas[area_id]["code"], "days": n_days,
                    "rain_total": round(sum(rain), 1) if rain else None, "rain_days": len(rain),
                    "temp_mean": round(sum(temp) / len(temp), 1) if temp else None, "temp_days": len(temp),
                    "humidity_mean": round(sum(hum) / len(hum), 1) if hum else None, "humidity_days": len(hum)})
    return {"per_area": per, "sources": sorted({r["source"] for r in rows}),
            "summary": f"Tổng hợp {len(rows)} bản ghi thời tiết của {len(area_ids)} khu vực"}


def analyze_spatial_distribution(area_ids: list[int], end: str) -> dict:
    areas, per = _area_map(), []
    points = get_water_points(area_ids, end)["rows"]
    for area_id in area_ids:
        area = areas[area_id]
        active = [p for p in points if p["area_id"] == area_id and p["status"] == "active"]
        inside = sum(1 for p in active if geo.point_in_polygon(p["latitude"], p["longitude"], area["polygon"]))
        types: dict[str, int] = {}
        for p in active:
            types[p["water_type"] or "khác"] = types.get(p["water_type"] or "khác", 0) + 1
        per.append({"area_id": area_id, "area_code": area["code"], "active": len(active), "inside_polygon": inside,
                    "total_recorded": sum(1 for p in points if p["area_id"] == area_id), "by_type": types})
    per.sort(key=lambda x: x["active"], reverse=True)
    return {"per_area": per, "sources": sorted({p["source"] for p in points}),
            "summary": f"Phân bố {sum(x['active'] for x in per)} điểm nước đọng đang tồn tại trên {len(per)} khu vực"}


def summarize_surveys(area_ids: list[int], start: str, end: str, species: str) -> dict:
    rows = [r for r in get_survey_data(area_ids, end, species)["rows"] if r["survey_date"] >= start]
    areas, per = _area_map(), []
    for area_id in area_ids:
        mine = [r for r in rows if r["area_id"] == area_id]
        valid = [r for r in mine if r["result"] != "not_surveyed"]
        positive = [r for r in valid if r["result"] in ("larvae_present", "adult_present")]
        per.append({"area_id": area_id, "area_code": areas[area_id]["code"], "records": len(mine), "valid": len(valid),
                    "positive": len(positive), "not_surveyed": len(mine) - len(valid),
                    "positive_ratio": round(len(positive) / len(valid), 2) if valid else None})
    return {"per_area": per, "sources": sorted({r["source"] for r in rows}),
            "summary": f"{len(rows)} bản ghi khảo sát trong kỳ của {len(area_ids)} khu vực"}


def get_alerts(area_ids: list[int], status: str | None = None) -> dict:
    items = [a for a in alert_service.list_alerts(status=status) if a["area_id"] in area_ids]
    slim = [{k: a[k] for k in ("id", "code", "area_code", "type_label", "severity", "severity_label", "status",
                               "status_label", "ess", "pis", "created_at")} for a in items]
    return {"alerts": slim, "summary": f"{len(slim)} cảnh báo/đề xuất" + (f" ở trạng thái {status}" if status else "")}


TOOLS: dict[str, Callable[..., dict]] = {
    "get_weather_data": get_weather_data,
    "get_water_points": get_water_points,
    "get_survey_data": get_survey_data,
    "validate_dataset": validate_dataset,
    "compute_environmental_score": compute_environmental_score,
    "build_map_layer": build_map_layer,
    "rank_priority_locations": rank_priority_locations,
    "create_alert_proposals": create_alert_proposals,
    "get_environmental_score": get_environmental_score,
    "summarize_weather": summarize_weather,
    "analyze_spatial_distribution": analyze_spatial_distribution,
    "summarize_surveys": summarize_surveys,
    "get_alerts": get_alerts,
}

# Chính sách công cụ (Tool Guardrails): Agent nào được gọi, công cụ có GHI dữ liệu hay không.
_DATA, _ENV, _GEO, _RISK = "Data Agent", "Environmental Analysis Agent", "Geospatial Agent", "Risk & Alert Agent"
TOOL_POLICY: dict[str, dict] = {
    "get_weather_data": {"agents": [_DATA], "writes": False},
    "get_water_points": {"agents": [_DATA], "writes": False},
    "get_survey_data": {"agents": [_DATA], "writes": False},
    "validate_dataset": {"agents": [_DATA], "writes": False},
    "compute_environmental_score": {"agents": [_ENV], "writes": True, "writes_what": "lưu một lần phân tích (analysis_runs)"},
    "build_map_layer": {"agents": [_GEO], "writes": False},
    "rank_priority_locations": {"agents": [_RISK], "writes": False},
    "create_alert_proposals": {"agents": [_RISK], "writes": True, "writes_what": "tạo đề xuất ở trạng thái CHỜ DUYỆT"},
    "get_environmental_score": {"agents": [_ENV], "writes": False},
    "summarize_weather": {"agents": [_DATA], "writes": False},
    "analyze_spatial_distribution": {"agents": [_GEO], "writes": False},
    "summarize_surveys": {"agents": [_DATA], "writes": False},
    "get_alerts": {"agents": [_RISK], "writes": False},
}
assert set(TOOL_POLICY) == set(TOOLS)


def tool_catalog() -> list[dict]:
    return [{"name": name, **policy} for name, policy in TOOL_POLICY.items()]


class ToolRunner:
    """Gọi công cụ, ghi log từng lần thử, retry có giới hạn và kiểm tra yêu cầu hủy."""

    def __init__(self, task_id: str, trace_id: str, fault: dict | None = None, backoff: float = 0.4,
                 read_only: bool = False):
        self.read_only = read_only
        self.task_id = task_id
        self.trace_id = trace_id
        self.fault = fault or {}
        self.backoff = backoff
        self.step_key = "intake"
        self.retries_used = 0

    def _maybe_inject_fault(self, tool: str, attempt: int) -> None:
        """Lỗi MÔ PHỎNG phục vụ kiểm thử xử lý lỗi (TC05). Chỉ bật khi người dùng chọn trong form nhiệm vụ."""
        mode = self.fault.get("mode")
        if not mode or mode == "none" or self.fault.get("tool", "get_weather_data") != tool:
            return
        if mode == "permanent" or (mode == "transient" and attempt == 1):
            raise ToolError("TOOL_UNAVAILABLE", "Nguồn dữ liệu không phản hồi (lỗi mô phỏng để kiểm thử).", retryable=True)

    def call(self, agent: str, tool: str, **kwargs: Any) -> dict:
        if tool not in TOOLS:
            raise ToolError("TOOL_NOT_ALLOWED", f"Công cụ “{tool}” không có trong danh mục cho phép.", retryable=False)
        policy = TOOL_POLICY[tool]
        denied = None
        if agent not in policy["agents"]:
            denied = ("TOOL_NOT_ALLOWED", f"{agent} không được cấp quyền dùng công cụ “{tool}”.")
        elif self.read_only and policy["writes"]:
            denied = ("WRITE_NOT_ALLOWED", f"Công cụ “{tool}” ghi dữ liệu nên bị chặn trong chế độ chỉ đọc.")
        if denied:
            db.execute(
                """INSERT INTO tool_calls (task_id, trace_id, step_key, agent, tool, attempt, input, output, status,
                   error_code, error_message, started_at, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.task_id, self.trace_id, self.step_key, agent, tool, 1, db.dumps(sanitize(kwargs)), None, "denied",
                 denied[0], denied[1], db.now_iso(), 0))
            raise ToolError(denied[0], denied[1], retryable=False)
        attempt = 0
        while True:
            attempt += 1
            row = db.query_one("SELECT cancel_requested FROM tasks WHERE id=?", (self.task_id,))
            if row and row["cancel_requested"]:
                raise TaskCancelled()
            started = db.now_iso()
            t0 = time.perf_counter()
            try:
                self._maybe_inject_fault(tool, attempt)
                output = TOOLS[tool](**kwargs)
                duration = int((time.perf_counter() - t0) * 1000)
                summary = {"summary": output.get("summary")}
                if "sources" in output:
                    summary["sources"] = output["sources"]
                db.execute(
                    """INSERT INTO tool_calls (task_id, trace_id, step_key, agent, tool, attempt, input, output, status,
                       started_at, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.task_id, self.trace_id, self.step_key, agent, tool, attempt, db.dumps(sanitize(kwargs)),
                     db.dumps(summary), "success", started, duration))
                return output
            except ToolError as exc:
                duration = int((time.perf_counter() - t0) * 1000)
                will_retry = exc.retryable and attempt <= MAX_RETRIES
                db.execute(
                    """INSERT INTO tool_calls (task_id, trace_id, step_key, agent, tool, attempt, input, output, status,
                       error_code, error_message, started_at, duration_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (self.task_id, self.trace_id, self.step_key, agent, tool, attempt, db.dumps(sanitize(kwargs)), None,
                     "retrying" if will_retry else "failed", exc.code, exc.message, started, duration))
                if not will_retry:
                    raise
                self.retries_used += 1
                db.execute("UPDATE tasks SET retry_count = retry_count + 1 WHERE id=?", (self.task_id,))
                time.sleep(self.backoff * attempt)
