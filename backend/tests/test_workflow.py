"""Test validation, đặc trưng, workflow Agent, phê duyệt và phân quyền trên dữ liệu mẫu."""
import pytest
from fastapi import HTTPException

from app import db
from app.agents import orchestrator
from app.security import check_permission
from app.services import alerts, analysis, geo, testcases, validation
from app.services.features import DataSnapshot

ANALYST = {"id": 2, "full_name": "Analyst test", "role": "analyst"}
OFFICER = {"id": 3, "full_name": "Officer test", "role": "officer"}


def window():
    return analysis.default_window(DataSnapshot())


def area(code):
    return next(a for a in geo.load_areas() if a["code"] == code)


def test_weather_validation_reports_row_field_and_fix():
    report = validation.validate_rows("weather", [
        {"area_code": "KV-A", "date": "2020-01-01", "rainfall_mm": "12", "temperature_c": "28", "humidity_pct": "80"},
        {"area_code": "KV-ZZ", "date": "2020-01-02", "rainfall_mm": "12"},
        {"area_code": "KV-A", "date": "01-2020", "rainfall_mm": "abc", "humidity_pct": "140"},
        {"area_code": "KV-B", "date": "2020-01-03", "rainfall_mm": "", "temperature_c": "27", "humidity_pct": ""},
    ])
    rows = report["rows"]
    assert [r["valid"] for r in rows] == [True, False, False, True]
    assert rows[1]["errors"][0]["field"] == "area_code" and rows[1]["errors"][0]["fix"]
    assert {e["field"] for e in rows[2]["errors"]} == {"date", "rainfall_mm", "humidity_pct"}
    assert rows[3]["data"]["rainfall_mm"] is None  # để trống = thiếu, không phải 0


def test_coordinates_outside_or_swapped_are_rejected():
    a = area("KV-A")
    report = validation.validate_rows("water", [
        {"latitude": a["centroid_lng"], "longitude": a["centroid_lat"], "water_type": "Vũng nước", "observed_date": "2020-01-01"},
        {"latitude": 10.0, "longitude": 106.0, "water_type": "Vũng nước", "observed_date": "2020-01-01"},
    ])
    assert not report["rows"][0]["valid"] and "đảo" in report["rows"][0]["errors"][0]["message"]
    assert not report["rows"][1]["valid"]


def test_existing_records_are_not_overwritten_without_policy():
    start, end = window()
    row = {"area_code": "KV-H", "date": end, "rainfall_mm": "99"}
    before = db.query_one("SELECT rainfall_mm FROM weather WHERE area_id=? AND obs_date=?", (area("KV-H")["id"], end))
    result = validation.commit_rows("weather", [row], "tester", None, "skip")
    after = db.query_one("SELECT rainfall_mm FROM weather WHERE area_id=? AND obs_date=?", (area("KV-H")["id"], end))
    assert result["skipped"] == 1 and result["updated"] == 0 and before == after


def test_not_surveyed_is_not_evidence_of_absence():
    start, end = window()
    snap = DataSnapshot()
    e = analysis.evaluate(snap, area("KV-E")["id"], start, end)   # chỉ có bản ghi "chưa khảo sát"
    survey = next(c for c in e["components"] if c["key"] == "survey")
    assert survey["missing"] and survey["score"] is None and e["status"] == "partial"
    b = analysis.evaluate(snap, area("KV-B")["id"], start, end)   # đã khảo sát, không ghi nhận
    assert next(c for c in b["components"] if c["key"] == "survey")["score"] == 10


def test_missing_humidity_area_is_flagged():
    start, end = window()
    d = analysis.evaluate(DataSnapshot(), area("KV-D")["id"], start, end)
    assert "humidity" in [m["key"] for m in d["missing"]] and d["completeness"] == pytest.approx(0.85)


def run_task(areas, fault="none"):
    start, end = window()
    task = orchestrator.create_task("Phân tích điều kiện môi trường (pytest)", {
        "area_ids": [area(c)["id"] for c in areas], "start": start, "end": end, "species": "aedes",
        "sources": ["weather", "water", "survey"], "simulate_fault": fault}, ANALYST, is_test=True)
    orchestrator.start_task(task["id"], sync=True, step_delay=0)
    return orchestrator.get_task(task["id"])


def test_workflow_end_to_end_with_human_approval():
    task = run_task(["KV-A", "KV-B"])
    assert task["status"] == "waiting_approval"
    assert [s["status"] for s in task["steps"]] == ["success"] * 6 + ["waiting", "pending"]
    agents = {c["agent"] for c in task["tool_calls"]}
    assert agents == {"Data Agent", "Environmental Analysis Agent", "Geospatial Agent", "Risk & Alert Agent"}
    assert len(task["result"]["run_ids"]) == 2 and task["result"]["scoring_version"]
    alert_id = task["result"]["alert_ids"][0]
    with pytest.raises(HTTPException) as exc:
        alerts.decide(alert_id, "reject", "", OFFICER)       # từ chối bắt buộc có ghi chú
    assert exc.value.status_code == 422
    decided = alerts.decide(alert_id, "approve", "Đồng ý kiểm tra", OFFICER)
    assert decided["status"] == "approved"
    assert decided["history"][-1]["actor"] == "Officer test" and decided["history"][-1]["action"] == "approved"
    assert orchestrator.get_task(task["id"])["status"] == "completed"


def test_tool_failure_never_reports_completed():
    task = run_task(["KV-C"], fault="permanent")
    assert task["status"] == "failed" and task["retry_count"] == 2
    assert [c["status"] for c in task["tool_calls"]] == ["retrying", "retrying", "failed"]
    assert db.query_one("SELECT COUNT(*) AS n FROM analysis_runs WHERE task_id=?", (task["id"],))["n"] == 0


def test_transient_failure_recovers_after_retry():
    task = run_task(["KV-F"], fault="transient")
    assert task["status"] in ("waiting_approval", "completed") and task["retry_count"] == 1


def test_only_authorised_roles_can_approve():
    for role, allowed in (("viewer", False), ("analyst", False), ("officer", True), ("admin", True)):
        if allowed:
            check_permission({"role": role, "full_name": role}, "alert.approve")
        else:
            with pytest.raises(HTTPException) as exc:
                check_permission({"role": role, "full_name": role}, "alert.approve")
            assert exc.value.status_code == 403


def test_out_of_scope_objective_gets_guardrail_note():
    from app.agents.llm import SimulatedLLM
    intent = SimulatedLLM().classify_intent("Dự đoán số ca bệnh tuần tới")
    assert intent["out_of_scope_terms"] and "không chẩn đoán" in intent["guardrail_note"]


def test_builtin_suite_passes():
    result = testcases.run_suite("pytest")
    assert result["passed"] == result["total"] == 6
