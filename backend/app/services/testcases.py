"""Bộ 6 tình huống kiểm thử (TC01–TC06). Mỗi lần chạy thực thi mã thật và lưu expected/actual/pass-fail."""
from __future__ import annotations

import time
import uuid

from fastapi import HTTPException

from .. import db
from ..agents import orchestrator
from ..security import check_permission
from . import analysis, geo, scoring, validation
from .features import DataSnapshot

SYSTEM_USER = {"id": 0, "full_name": "Bộ test tự động", "role": "admin"}


def _features(rain, temp, hum, water, survey):
    return {"rainfall_7d": rain, "temperature_mean": temp, "humidity_mean": hum, "water_points_active": water,
            "survey_positive_ratio": survey, "_meta": {}}


def _slim(result: dict) -> dict:
    return {"status": result["status"], "ess": result["ess"],
            "ess_class": result["ess_class"]["label"] if result["ess_class"] else None,
            "completeness": result["completeness"],
            "component_scores": {c["key"]: c["score"] for c in result["components"]},
            "missing": [m["key"] for m in result["missing"]], "version": result["version"]}


def tc01() -> dict:
    inputs = {"rainfall_7d": 40, "temperature_mean": 27.5, "humidity_mean": 72, "water_points_active": 5, "survey_positive_ratio": 1 / 3}
    first = scoring.compute_ess(_features(40, 27.5, 72, 5, 1 / 3))
    second = scoring.compute_ess(_features(40, 27.5, 72, 5, 1 / 3))
    # Tính tay độc lập: 0.25×40 + 0.20×100 + 0.15×64 + 0.25×33.3 + 0.15×40 = 53.9
    expected_ess = 53.9
    passed = (first["status"] == "ok" and first["completeness"] == 1.0 and abs(first["ess"] - expected_ess) <= 0.1
              and first["ess_class"]["key"] == "medium" and _slim(first) == _slim(second))
    return {"title": "Dữ liệu đầy đủ, điều kiện môi trường thông thường", "input": inputs,
            "expected": {"status": "ok", "completeness": 1.0, "ess": expected_ess, "ess_class": "Trung bình",
                         "repeatable": "Hai lần chạy cho kết quả giống hệt nhau"},
            "actual": {**_slim(first), "repeat_identical": _slim(first) == _slim(second)}, "passed": passed,
            "comment": "ESS khớp phép tính tay theo công thức đã công bố và lặp lại được." if passed else "ESS lệch so với phép tính tay hoặc không lặp lại được."}


def tc02() -> dict:
    before = scoring.compute_ess(_features(20, 28, 60, 2, 0.25))
    after = scoring.compute_ess(_features(90, 28, 85, 14, 0.25))
    sb, sa = _slim(before)["component_scores"], _slim(after)["component_scores"]
    passed = (after["ess"] > before["ess"] and all(sa[k] > sb[k] for k in ("rainfall", "humidity", "water"))
              and sa["temperature"] == sb["temperature"] and sa["survey"] == sb["survey"]
              and before["ess_class"]["key"] != after["ess_class"]["key"])
    return {"title": "Mưa/độ ẩm tăng và có thêm điểm nước đọng",
            "input": {"before": {"rainfall_7d": 20, "humidity_mean": 60, "water_points_active": 2},
                      "after": {"rainfall_7d": 90, "humidity_mean": 85, "water_points_active": 14},
                      "unchanged": {"temperature_mean": 28, "survey_positive_ratio": 0.25}},
            "expected": {"ess": "Tăng", "components_increase": ["rainfall", "humidity", "water"],
                         "components_unchanged": ["temperature", "survey"], "class": "Chuyển nhóm cao hơn"},
            "actual": {"before": _slim(before), "after": _slim(after)}, "passed": passed,
            "comment": "Điểm thành phần và nhóm đánh giá thay đổi đúng theo quy tắc." if passed else "Thay đổi không đúng quy tắc đã công bố."}


def tc03() -> dict:
    partial = scoring.compute_ess(_features(60, 28, None, 8, 0.5))
    insufficient = scoring.compute_ess(_features(60, None, None, None, 0.5))
    hum = next(c for c in partial["components"] if c["key"] == "humidity")
    # Tính tay với trọng số chia lại trên 0.85: (0.25×60 + 0.20×100 + 0.25×53.3 + 0.15×55) / 0.85 = 66.6
    expected_ess = 66.6
    passed = (partial["status"] == "partial" and hum["score"] is None and hum["missing"] and partial["completeness"] == 0.85
              and "humidity" in [m["key"] for m in partial["missing"]] and abs(partial["ess"] - expected_ess) <= 0.1
              and insufficient["status"] == "insufficient_data" and insufficient["ess"] is None)
    return {"title": "Thiếu nhiệt độ hoặc độ ẩm",
            "input": {"case_a": {"humidity_mean": None, "others": "đầy đủ"},
                      "case_b": {"temperature_mean": None, "humidity_mean": None, "water_points_active": None}},
            "expected": {"case_a": {"status": "partial", "humidity_score": None, "completeness": 0.85, "ess": expected_ess,
                                    "note": "Không coi thiếu là 0; chia lại trọng số"},
                         "case_b": {"status": "insufficient_data", "ess": None}},
            "actual": {"case_a": _slim(partial), "case_b": {**_slim(insufficient), "message": insufficient["message"]}},
            "passed": passed,
            "comment": "Báo thiếu dữ liệu, không bịa giá trị; dưới ngưỡng đầy đủ thì không tính ESS." if passed else "Chính sách thiếu dữ liệu không được áp dụng đúng."}


def tc04() -> dict:
    areas = geo.load_areas()
    good = areas[0]
    today = db.now_iso()[:10]
    rows = [
        {"latitude": good["centroid_lat"], "longitude": good["centroid_lng"], "water_type": "Lốp xe cũ", "observed_date": today},
        {"latitude": 91.5, "longitude": good["centroid_lng"], "water_type": "Vũng nước", "observed_date": today},
        {"latitude": good["centroid_lng"], "longitude": good["centroid_lat"], "water_type": "Chum/vại", "observed_date": today},
        {"latitude": 10.7769, "longitude": 106.7009, "water_type": "Cống rãnh", "observed_date": today},
    ]
    before = db.query_one("SELECT COUNT(*) AS n FROM water_points")["n"]
    report = validation.validate_rows("water", rows)
    after = db.query_one("SELECT COUNT(*) AS n FROM water_points")["n"]
    actual_rows = [{"row": r["row"], "valid": r["valid"], "errors": [e["message"] for e in r["errors"]],
                    "fix": [e["fix"] for e in r["errors"]]} for r in report["rows"]]
    passed = ([r["valid"] for r in report["rows"]] == [True, False, False, False] and before == after
              and "đảo" in " ".join(actual_rows[2]["errors"]))
    return {"title": "Tọa độ sai hoặc ngoài phạm vi", "input": rows,
            "expected": {"valid_rows": [1], "rejected_rows": [2, 3, 4],
                         "notes": ["Dòng 2: vĩ độ ngoài −90…90", "Dòng 3: phát hiện đảo vĩ độ/kinh độ",
                                   "Dòng 4: ngoài khu vực thí điểm, không gắn lên bản đồ"], "records_written": 0},
            "actual": {"summary": report["summary"], "rows": actual_rows, "records_written": after - before}, "passed": passed,
            "comment": "Dòng lỗi bị từ chối kèm lý do và cách sửa; không ghi gì vào CSDL ở bước kiểm tra." if passed else "Validation tọa độ chưa đúng."}


def tc05() -> dict:
    snapshot = DataSnapshot()
    window = analysis.default_window(snapshot)
    area_id = geo.load_areas()[0]["id"]
    params = {"area_ids": [area_id], "start": window[0], "end": window[1], "species": "aedes",
              "sources": ["weather", "water", "survey"], "simulate_fault": "permanent", "notes": "TC05"}
    task = orchestrator.create_task("TC05 — kiểm thử lỗi công cụ truy xuất dữ liệu", params, SYSTEM_USER, is_test=True)
    orchestrator.start_task(task["id"], sync=True, step_delay=0)
    task = orchestrator.get_task(task["id"])
    attempts = [c for c in task["tool_calls"] if c["tool"] == "get_weather_data"]
    runs = db.query_one("SELECT COUNT(*) AS n FROM analysis_runs WHERE task_id=?", (task["id"],))["n"]
    alerts = db.query_one("SELECT COUNT(*) AS n FROM alerts WHERE task_id=?", (task["id"],))["n"]
    actual = {"task_id": task["id"], "trace_id": task["trace_id"], "final_status": task["status"], "retry_count": task["retry_count"],
              "attempts": [{"attempt": c["attempt"], "status": c["status"], "error_code": c["error_code"]} for c in attempts],
              "steps": {s["key"]: s["status"] for s in task["steps"]}, "analysis_runs_created": runs, "alerts_created": alerts}
    passed = (task["status"] == "failed" and len(attempts) == 3 and task["retry_count"] == 2
              and attempts[-1]["status"] == "failed" and runs == 0 and alerts == 0 and task["steps"][-1]["status"] != "success")
    return {"title": "Tool/API truy xuất dữ liệu gặp lỗi", "input": {**params, "note": "Lỗi được mô phỏng trong ToolRunner"},
            "expected": {"final_status": "failed (không báo hoàn thành giả)", "attempts": 3, "retry_count": 2,
                         "analysis_runs_created": 0, "alerts_created": 0},
            "actual": actual, "passed": passed,
            "comment": "Retry có giới hạn (2 lần), ghi log từng lần thử, kết thúc an toàn ở trạng thái Thất bại." if passed else "Xử lý lỗi công cụ chưa đúng."}


def tc06() -> dict:
    outcomes = {}
    for role in ("viewer", "analyst", "officer", "admin"):
        try:
            check_permission({"role": role, "full_name": role}, "alert.approve")
            outcomes[role] = {"allowed": True}
        except HTTPException as exc:
            outcomes[role] = {"allowed": False, "http_status": exc.status_code, "message": exc.detail}
    passed = (not outcomes["viewer"]["allowed"] and outcomes["viewer"]["http_status"] == 403
              and not outcomes["analyst"]["allowed"] and outcomes["officer"]["allowed"] and outcomes["admin"]["allowed"])
    return {"title": "Người dùng không có quyền phê duyệt",
            "input": {"permission": "alert.approve", "roles": ["viewer", "analyst", "officer", "admin"]},
            "expected": {"viewer": "403 + thông báo quyền", "analyst": "403 (người tạo đề xuất không tự duyệt)",
                         "officer": "được phép", "admin": "được phép"},
            "actual": outcomes, "passed": passed,
            "comment": "Kiểm tra ở lớp phân quyền mà API phê duyệt sử dụng; giao diện đồng thời ẩn/khóa nút duyệt." if passed else "Phân quyền phê duyệt chưa đúng."}


CASES = [("TC01", tc01), ("TC02", tc02), ("TC03", tc03), ("TC04", tc04), ("TC05", tc05), ("TC06", tc06)]


def run_suite(user_name: str) -> dict:
    suite_id = f"SUITE-{uuid.uuid4().hex[:8].upper()}"
    run_at = db.now_iso()
    for code, func in CASES:
        t0 = time.perf_counter()
        try:
            outcome = func()
        except Exception as exc:  # một ca lỗi không làm hỏng cả bộ
            outcome = {"title": code, "input": {}, "expected": {}, "actual": {"error": f"{type(exc).__name__}: {exc}"},
                       "passed": False, "comment": "Ca kiểm thử gặp lỗi khi chạy."}
        duration = int((time.perf_counter() - t0) * 1000)
        db.execute(
            """INSERT INTO test_runs (suite_run_id, case_code, title, input, expected, actual, passed, comment, duration_ms, run_at, run_by)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (suite_id, code, outcome["title"], db.dumps(outcome["input"]), db.dumps(outcome["expected"]),
             db.dumps(outcome["actual"]), 1 if outcome["passed"] else 0, outcome["comment"], duration, run_at, user_name))
    return latest()


def latest() -> dict:
    last = db.query_one("SELECT suite_run_id, run_at, run_by FROM test_runs ORDER BY id DESC LIMIT 1")
    if not last:
        return {"suite_run_id": None, "cases": [], "scoring_version": scoring.SCORING_VERSION,
                "definitions": [{"case_code": code, "title": func.__doc__ or code} for code, func in CASES]}
    rows = db.query("SELECT * FROM test_runs WHERE suite_run_id=? ORDER BY id", (last["suite_run_id"],))
    for row in rows:
        for key in ("input", "expected", "actual"):
            row[key] = db.loads(row[key])
        row["passed"] = bool(row["passed"])
    history = db.query("""SELECT suite_run_id, MIN(run_at) AS run_at, MIN(run_by) AS run_by, SUM(passed) AS passed, COUNT(*) AS total
                          FROM test_runs GROUP BY suite_run_id ORDER BY MIN(id) DESC LIMIT 10""")
    return {"suite_run_id": last["suite_run_id"], "run_at": last["run_at"], "run_by": last["run_by"], "cases": rows,
            "passed": sum(1 for r in rows if r["passed"]), "total": len(rows), "history": history,
            "scoring_version": scoring.SCORING_VERSION}
