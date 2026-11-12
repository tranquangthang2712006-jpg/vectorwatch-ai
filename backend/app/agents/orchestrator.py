"""Orchestrator: phân loại yêu cầu, lập kế hoạch, điều phối 4 Agent, theo dõi trạng thái, ghi log, xử lý lỗi.

Máy trạng thái nhiệm vụ: queued → running → (waiting_approval) → completed | failed | cancelled.
Nhiệm vụ KHÔNG bao giờ được đánh dấu completed nếu có bước thất bại.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import date, datetime

from fastapi import HTTPException

from .. import config, db
from ..services import geo, scoring
from .base import StepResult, TaskContext
from .llm import get_llm
from .specialists import DataAgent, EnvironmentalAnalysisAgent, GeospatialAgent, RiskAlertAgent
from .tools import TaskCancelled, ToolError, ToolRunner

STATUS_LABELS = {"queued": "Đang chờ", "running": "Đang thực hiện", "waiting_approval": "Chờ phê duyệt",
                 "completed": "Hoàn thành", "failed": "Thất bại", "cancelled": "Đã hủy"}
VALID_SOURCES = ("weather", "water", "survey")
MAX_WINDOW_DAYS = 31


# ---------------------------------------------------------------------------
# Tạo / đọc nhiệm vụ
# ---------------------------------------------------------------------------
def create_task(objective: str, params: dict, user: dict, is_test: bool = False) -> dict:
    objective = (objective or "").strip()
    if len(objective) < 5:
        raise HTTPException(422, "Hãy mô tả mục tiêu phân tích (ít nhất 5 ký tự).")
    species = params.get("species", "aedes")
    spec = scoring.SPECIES_REGISTRY.get(species)
    if not spec or not spec.get("configured"):
        raise HTTPException(422, f"Loài “{species}” chưa có bộ tham số trong MVP. Hãy chọn Aedes.")
    areas = {a["id"] for a in geo.load_areas()}
    area_ids = [int(a) for a in params.get("area_ids") or []]
    if not area_ids or any(a not in areas for a in area_ids):
        raise HTTPException(422, "Hãy chọn ít nhất một khu vực hợp lệ.")
    try:
        start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
    except (KeyError, ValueError):
        raise HTTPException(422, "Khoảng thời gian không hợp lệ. Nhập ngày bắt đầu và kết thúc dạng YYYY-MM-DD.")
    if start > end:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise HTTPException(422, f"Khoảng thời gian tối đa {MAX_WINDOW_DAYS} ngày cho một lần phân tích.")
    sources = [s for s in params.get("sources") or [] if s in VALID_SOURCES]
    if not sources:
        raise HTTPException(422, "Hãy chọn ít nhất một nguồn dữ liệu.")
    fault_mode = (params.get("simulate_fault") or "none")
    if fault_mode not in ("none", "transient", "permanent"):
        raise HTTPException(422, "Chế độ mô phỏng lỗi không hợp lệ.")

    clean = {"area_ids": sorted(area_ids), "start": start.isoformat(), "end": end.isoformat(), "species": species,
             "sources": sources, "notes": (params.get("notes") or "").strip()[:500], "simulate_fault": fault_mode,
             "rerun_count": 0}
    if not is_test:
        for other in db.query("SELECT id, params FROM tasks WHERE status IN ('queued','running') AND is_test=0"):
            p = db.loads(other["params"], {})
            if all(p.get(k) == clean[k] for k in ("area_ids", "start", "end", "species", "sources")):
                raise HTTPException(409, f"Nhiệm vụ {other['id']} với cùng phạm vi đang chạy. Hãy chờ nó kết thúc hoặc hủy trước khi tạo bản chạy trùng.")

    task_id = f"TASK-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    llm = get_llm()
    llm.ref = task_id
    intent = llm.classify_intent(objective)
    plan = llm.plan(intent, clean)
    trace_id = uuid.uuid4().hex
    db.execute(
        """INSERT INTO tasks (id, trace_id, objective, params, status, current_step, plan, llm_mode, is_test, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (task_id, trace_id, objective, db.dumps(clean), "queued", plan[0]["key"], db.dumps({"intent": intent, "steps": plan}),
         llm.description, 1 if is_test else 0, user["full_name"], db.now_iso()))
    _create_steps(task_id, plan)
    return get_task(task_id)


def _create_steps(task_id: str, plan: list[dict]) -> None:
    db.execute("DELETE FROM task_steps WHERE task_id=?", (task_id,))
    for idx, step in enumerate(plan):
        db.execute("INSERT INTO task_steps (task_id, idx, key, label, agent, status) VALUES (?,?,?,?,?,'pending')",
                   (task_id, idx, step["key"], step["label"], step["agent"]))


def get_task(task_id: str, with_logs: bool = True) -> dict:
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not task:
        raise HTTPException(404, "Không tìm thấy nhiệm vụ. Hãy kiểm tra lại mã nhiệm vụ.")
    return _hydrate(task, with_logs)


def _hydrate(task: dict, with_logs: bool) -> dict:
    task["params"] = db.loads(task["params"], {})
    task["plan"] = db.loads(task["plan"], {})
    task["result"] = db.loads(task["result"])
    task["error"] = db.loads(task["error"])
    task["status_label"] = STATUS_LABELS.get(task["status"], task["status"])
    # llm_mode lưu mô tả chế độ tại thời điểm tạo nhiệm vụ (bản ghi cũ lưu "simulated").
    task["llm_description"] = "Mô phỏng theo luật (không gọi mô hình ngôn ngữ)" if task["llm_mode"] == "simulated" else task["llm_mode"]
    steps = db.query("SELECT * FROM task_steps WHERE task_id=? ORDER BY idx", (task["id"],))
    for step in steps:
        step["detail"] = db.loads(step["detail"])
    task["steps"] = steps
    current = next((s for s in steps if s["status"] in ("running", "waiting", "failed")), None)
    pending = next((s for s in steps if s["status"] == "pending"), None)
    task["current_step_label"] = current["label"] if current else None
    task["next_step_label"] = pending["label"] if pending and task["status"] in ("queued", "running", "waiting_approval") else None
    done = [s for s in steps if s["status"] in ("success", "skipped")]
    task["checkpoint"] = done[-1]["key"] if done else None
    if with_logs:
        calls = db.query("SELECT * FROM tool_calls WHERE task_id=? ORDER BY id", (task["id"],))
        for call in calls:
            call["input"] = db.loads(call["input"])
            call["output"] = db.loads(call["output"])
        task["tool_calls"] = calls
    return task


def list_tasks(limit: int = 30) -> list[dict]:
    rows = db.query("SELECT * FROM tasks WHERE is_test=0 ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_hydrate(r, with_logs=False) for r in rows]


# ---------------------------------------------------------------------------
# Thực thi
# ---------------------------------------------------------------------------
def start_task(task_id: str, sync: bool = False, step_delay: float | None = None) -> None:
    delay = config.STEP_DELAY if step_delay is None else step_delay
    if sync:
        run_task(task_id, delay)
    else:
        threading.Thread(target=run_task, args=(task_id, delay), daemon=True, name=f"task-{task_id}").start()


def _set_step(task_id: str, key: str, status: str, summary: str | None = None, detail: dict | None = None,
              start: bool = False, end: bool = False) -> None:
    sets, params = ["status=?"], [status]
    if summary is not None:
        sets.append("summary=?"); params.append(summary)
    if detail is not None:
        sets.append("detail=?"); params.append(db.dumps(detail))
    if start:
        sets.append("started_at=?"); params.append(db.now_iso())
    if end:
        sets.append("ended_at=?"); params.append(db.now_iso())
    db.execute(f"UPDATE task_steps SET {', '.join(sets)} WHERE task_id=? AND key=?", (*params, task_id, key))


def _skip_remaining(task_id: str, reason: str) -> None:
    db.execute("UPDATE task_steps SET status='skipped', summary=? WHERE task_id=? AND status='pending'", (reason, task_id))


def run_task(task_id: str, step_delay: float = 0.0) -> None:
    task = get_task(task_id, with_logs=False)
    params = task["params"]
    runner = ToolRunner(task_id, task["trace_id"], {"mode": params.get("simulate_fault"), "tool": "get_weather_data"},
                        backoff=0.4 if step_delay else 0.0)
    ctx = TaskContext(task_id, task["trace_id"], task["created_by"], params["area_ids"], params["start"], params["end"],
                      params["species"], params["sources"], runner)
    data_agent, env_agent, geo_agent, risk_agent = DataAgent(), EnvironmentalAnalysisAgent(), GeospatialAgent(), RiskAlertAgent()

    def intake(_: TaskContext) -> StepResult:
        intent = task["plan"]["intent"]
        warnings = [intent["guardrail_note"]] if intent.get("guardrail_note") else []
        if params.get("simulate_fault") not in (None, "none"):
            warnings.append("Nhiệm vụ này bật MÔ PHỎNG LỖI công cụ get_weather_data để kiểm thử xử lý lỗi.")
        return StepResult(
            f"Phân loại ý định: {intent['intent']} ({intent['method']}). Lập kế hoạch {len(task['plan']['steps'])} bước cho "
            f"{len(params['area_ids'])} khu vực, {params['start']} → {params['end']}, loài {params['species']}.",
            {"intent": intent, "plan": [s["label"] for s in task["plan"]["steps"]]}, warnings)

    handlers = [("intake", intake), ("retrieve", data_agent.retrieve), ("validate", data_agent.validate),
                ("environment", env_agent.analyze), ("geospatial", geo_agent.map_results), ("propose", risk_agent.propose)]

    db.execute("UPDATE tasks SET status='running', started_at=?, error=NULL, ended_at=NULL WHERE id=?", (db.now_iso(), task_id))
    for key, handler in handlers:
        try:
            row = db.query_one("SELECT cancel_requested FROM tasks WHERE id=?", (task_id,))
            if row["cancel_requested"]:
                raise TaskCancelled()
            runner.step_key = key
            db.execute("UPDATE tasks SET current_step=? WHERE id=?", (key, task_id))
            _set_step(task_id, key, "running", start=True)
            if step_delay:
                time.sleep(step_delay)
            result = handler(ctx)
            _set_step(task_id, key, "success", result.summary, {**result.detail, "warnings": result.warnings}, end=True)
        except TaskCancelled:
            _set_step(task_id, key, "cancelled", "Đã dừng theo yêu cầu hủy.", end=True)
            _skip_remaining(task_id, "Bỏ qua vì nhiệm vụ đã bị hủy.")
            db.execute("UPDATE tasks SET status='cancelled', ended_at=? WHERE id=?", (db.now_iso(), task_id))
            return
        except ToolError as exc:
            message = (f"Bước “{key}” thất bại sau {runner.retries_used} lần thử lại: {exc.message} "
                       "Không có kết luận nào được tạo từ bước này. Bạn có thể nhấn “Thử lại” hoặc kiểm tra nguồn dữ liệu.")
            _set_step(task_id, key, "failed", message, {"error_code": exc.code}, end=True)
            _skip_remaining(task_id, "Bỏ qua vì bước trước thất bại.")
            db.execute("UPDATE tasks SET status='failed', error=?, ended_at=? WHERE id=?",
                       (db.dumps({"step": key, "code": exc.code, "message": message}), db.now_iso(), task_id))
            return
        except Exception as exc:  # lỗi không lường trước: không lộ stack trace ra giao diện
            message = (f"Bước “{key}” gặp lỗi nội bộ ({type(exc).__name__}). Không có kết luận nào được tạo. "
                       f"Hãy thử lại; nếu lặp lại, gửi trace_id {task['trace_id']} cho quản trị viên.")
            _set_step(task_id, key, "failed", message, {"error_code": "INTERNAL_ERROR"}, end=True)
            _skip_remaining(task_id, "Bỏ qua vì bước trước thất bại.")
            db.execute("UPDATE tasks SET status='failed', error=?, ended_at=? WHERE id=?",
                       (db.dumps({"step": key, "code": "INTERNAL_ERROR", "message": message}), db.now_iso(), task_id))
            return

    # --- Kết quả tổng hợp + chuyển sang chờ duyệt -----------------------
    results = ctx.state.get("results", [])
    alerts = ctx.state.get("alerts", [])
    scored = [r for r in results if r["ess"] is not None]
    vn = lambda iso: "/".join(reversed(iso.split("-")))  # noqa: E731
    facts = [f"Đã phân tích {len(results)} khu vực ({vn(params['start'])} → {vn(params['end'])}), tính được ESS cho {len(scored)} khu vực."]
    if ctx.state.get("ranking"):
        top = ctx.state["ranking"][0]
        facts.append(f"PIS cao nhất: {top['area_code']} ({top['pis']:g}, {top['pis_class']}).")
    facts.append(f"{len(alerts)} đề xuất chờ người có thẩm quyền duyệt." if alerts else "Không có khu vực nào đạt ngưỡng tạo đề xuất.")
    checks = verify_results(task_id, params, results, alerts)
    if not all(c["passed"] for c in checks):
        failed = "; ".join(c["detail"] for c in checks if not c["passed"])
        message = (f"Orchestrator xác minh kết quả KHÔNG đạt: {failed}. Không chuyển đề xuất sang phê duyệt; "
                   f"hãy báo quản trị viên kèm trace_id {task['trace_id']}.")
        _set_step(task_id, "approval", "failed", message, {"verification": checks, "error_code": "VERIFICATION_FAILED"}, start=True, end=True)
        _skip_remaining(task_id, "Bỏ qua vì xác minh kết quả không đạt.")
        db.execute("UPDATE alerts SET status='rejected', updated_at=? WHERE task_id=? AND status='pending'", (db.now_iso(), task_id))
        db.execute("UPDATE tasks SET status='failed', error=?, result=?, ended_at=? WHERE id=?",
                   (db.dumps({"step": "approval", "code": "VERIFICATION_FAILED", "message": message}),
                    db.dumps({"verification": checks}), db.now_iso(), task_id))
        return
    llm = get_llm()
    llm.ref = task_id
    summary_text, summary_by = llm.summarize(facts)
    result = {
        "summary": summary_text,
        "summary_generated_by": summary_by,
        "facts": facts,
        "verification": checks,
        "run_ids": [r["run_id"] for r in results],
        "alert_ids": [a["id"] for a in alerts],
        "alert_codes": [a["code"] for a in alerts],
        "ranking": ctx.state.get("ranking", []),
        "data_sources": ctx.state.get("data_sources", []),
        "missing": ctx.state.get("data_issues", []),
        "scoring_version": scoring.SCORING_VERSION,
        "period": {"start": params["start"], "end": params["end"]},
        "generated_at": db.now_iso(),
        "notice": scoring.DEMO_NOTICE,
    }
    db.execute("UPDATE tasks SET result=? WHERE id=?", (db.dumps(result), task_id))
    open_alerts = _open_alert_count(task_id)
    if open_alerts:
        _set_step(task_id, "approval", "waiting", f"{open_alerts} đề xuất đang chờ con người phê duyệt. Agent không tự phát hành hành động.",
                  start=True)
        db.execute("UPDATE tasks SET status='waiting_approval', current_step='approval' WHERE id=?", (task_id,))
    else:
        _set_step(task_id, "approval", "skipped", "Không có đề xuất cần duyệt.", end=True)
        _finish(task_id)


def verify_results(task_id: str, params: dict, results: list[dict], alerts: list[dict]) -> list[dict]:
    """Result Verification (đặc tả 16.6): đối chiếu kết quả ĐÃ LƯU với phạm vi nhiệm vụ trước khi đưa sang người duyệt."""
    run_ids = [r["run_id"] for r in results]
    marks = ",".join("?" * len(run_ids)) or "NULL"
    runs = db.query(f"SELECT id, area_id, start_date, end_date, scoring_version, ess, status, task_id, payload "
                    f"FROM analysis_runs WHERE id IN ({marks})", run_ids)
    checks = []

    def add(key: str, label: str, passed: bool, detail: str) -> None:
        checks.append({"key": key, "label": label, "passed": passed, "detail": detail})

    expected = sorted(params["area_ids"])
    got = sorted(r["area_id"] for r in runs)
    add("areas", "Đủ và đúng khu vực", got == expected,
        f"{len(got)}/{len(expected)} khu vực có kết quả đã lưu" if got == expected else "kết quả không khớp danh sách khu vực đã chọn")
    wrong_period = [r["id"] for r in runs if (r["start_date"], r["end_date"]) != (params["start"], params["end"])]
    add("period", "Đúng khoảng thời gian", not wrong_period,
        f"mọi kết quả thuộc kỳ {params['start']} → {params['end']}" if not wrong_period else f"lần chạy {wrong_period} sai kỳ")
    wrong_task = [r["id"] for r in runs if r["task_id"] != task_id]
    add("trace", "Kết quả gắn đúng nhiệm vụ", not wrong_task,
        "mọi lần phân tích ghi task_id của nhiệm vụ này" if not wrong_task else f"lần chạy {wrong_task} không gắn task_id")
    bad_version = [r["id"] for r in runs if r["scoring_version"] != scoring.SCORING_VERSION]
    add("version", "Có phiên bản công thức", not bad_version,
        f"scoring {scoring.SCORING_VERSION}" if not bad_version else f"lần chạy {bad_version} sai phiên bản công thức")
    unsourced, invented = [], []
    for r in runs:
        payload = db.loads(r["payload"], {})
        if r["ess"] is None:
            if r["status"] not in ("insufficient_data", "unsupported_species"):
                invented.append(r["id"])
            continue
        if any(not c["missing"] and not c.get("source") for c in payload.get("components", [])):
            unsourced.append(r["id"])
    add("sources", "Điểm số có nguồn dữ liệu", not unsourced,
        "mọi thành phần dùng để tính điểm đều có nguồn" if not unsourced else f"lần chạy {unsourced} có thành phần thiếu nguồn")
    add("no_invention", "Không suy diễn khi thiếu dữ liệu", not invented,
        "khu vực không đủ dữ liệu được để trống điểm" if not invented else f"lần chạy {invented} trạng thái không nhất quán")
    in_scope = set(expected)
    stray = [a["code"] for a in alerts if a.get("area_id") not in in_scope]
    rows = db.query("SELECT code, status FROM alerts WHERE task_id=?", (task_id,))
    auto_decided = [r["code"] for r in rows if r["status"] not in ("pending", "needs_revision")]
    add("human_approval", "Đề xuất chờ con người duyệt", not stray and not auto_decided,
        f"{len(rows)} đề xuất ở trạng thái chờ duyệt, không có đề xuất ngoài phạm vi"
        if not stray and not auto_decided else f"đề xuất bất thường: {', '.join(stray + auto_decided)}")
    return checks


def _open_alert_count(task_id: str) -> int:
    return db.query_one("SELECT COUNT(*) AS n FROM alerts WHERE task_id=? AND status IN ('pending','needs_revision')", (task_id,))["n"]


def _finish(task_id: str) -> None:
    _set_step(task_id, "done", "success", "Nhiệm vụ hoàn tất. Kết quả có ở trang Phân tích, Bản đồ, Cảnh báo và Báo cáo.",
              start=True, end=True)
    db.execute("UPDATE tasks SET status='completed', current_step='done', ended_at=? WHERE id=?", (db.now_iso(), task_id))


def refresh_after_decision(task_id: str) -> None:
    """Gọi sau mỗi quyết định duyệt: khi mọi đề xuất của nhiệm vụ đã có quyết định thì hoàn tất nhiệm vụ."""
    task = db.query_one("SELECT status FROM tasks WHERE id=?", (task_id,))
    if not task or task["status"] != "waiting_approval":
        return
    remaining = _open_alert_count(task_id)
    if remaining:
        _set_step(task_id, "approval", "waiting", f"Còn {remaining} đề xuất chờ quyết định.")
        return
    decided = db.query("SELECT status, COUNT(*) AS n FROM alerts WHERE task_id=? GROUP BY status", (task_id,))
    labels = {"approved": "đã phê duyệt", "rejected": "đã từ chối"}
    text = ", ".join(f"{d['n']} {labels.get(d['status'], d['status'])}" for d in decided)
    summary = (f"Mọi đề xuất đã có quyết định của con người ({text})." if decided else
               "Các đề xuất của nhiệm vụ này đã được gộp vào nhiệm vụ mới hơn (chống trùng); việc duyệt tiếp tục ở nhiệm vụ đó.")
    _set_step(task_id, "approval", "success", summary, end=True)
    _finish(task_id)


def cancel_task(task_id: str, user: dict, reason: str | None) -> dict:
    task = get_task(task_id, with_logs=False)
    if task["status"] not in ("queued", "running", "waiting_approval"):
        raise HTTPException(409, f"Nhiệm vụ đang ở trạng thái “{task['status_label']}” nên không thể hủy.")
    db.execute("UPDATE tasks SET cancel_requested=1, cancelled_by=?, cancel_reason=? WHERE id=?",
               (user["full_name"], (reason or "").strip() or None, task_id))
    if task["status"] in ("queued", "waiting_approval"):
        db.execute("UPDATE task_steps SET status='cancelled', summary='Đã hủy trước khi hoàn tất.', ended_at=? WHERE task_id=? AND status IN ('waiting','running')",
                   (db.now_iso(), task_id))
        _skip_remaining(task_id, "Bỏ qua vì nhiệm vụ đã bị hủy.")
        db.execute("UPDATE tasks SET status='cancelled', ended_at=? WHERE id=?", (db.now_iso(), task_id))
    return get_task(task_id)


def retry_task(task_id: str) -> dict:
    task = get_task(task_id, with_logs=False)
    if task["status"] != "failed":
        raise HTTPException(409, "Chỉ thử lại được nhiệm vụ đang ở trạng thái Thất bại.")
    params = task["params"]
    params["rerun_count"] = params.get("rerun_count", 0) + 1
    db.execute("UPDATE tasks SET status='queued', params=?, cancel_requested=0, error=NULL, result=NULL, ended_at=NULL WHERE id=?",
               (db.dumps(params), task_id))
    _create_steps(task_id, task["plan"]["steps"])
    start_task(task_id)
    return get_task(task_id)


def recover_interrupted() -> None:
    """Khi máy chủ khởi động lại: nhiệm vụ đang chạy dở được đánh dấu thất bại rõ ràng (không báo hoàn thành giả)."""
    for task in db.query("SELECT id FROM tasks WHERE status IN ('queued','running')"):
        message = "Nhiệm vụ bị gián đoạn do máy chủ khởi động lại. Nhấn “Thử lại” để chạy lại từ đầu."
        db.execute("UPDATE task_steps SET status='failed', summary=?, ended_at=? WHERE task_id=? AND status='running'",
                   (message, db.now_iso(), task["id"]))
        _skip_remaining(task["id"], "Bỏ qua vì nhiệm vụ bị gián đoạn.")
        db.execute("UPDATE tasks SET status='failed', error=?, ended_at=? WHERE id=?",
                   (db.dumps({"step": None, "code": "INTERRUPTED", "message": message}), db.now_iso(), task["id"]))
