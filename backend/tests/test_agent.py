"""Trợ lý hỏi đáp, chính sách công cụ, xác minh kết quả và lớp LLM thật (dùng máy chủ LLM giả cục bộ)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import config, db
from app.agents import assistant, llm, orchestrator
from app.agents.tools import ToolError, ToolRunner

ANALYST = {"id": 2, "full_name": "Chuyên viên test", "role": "analyst"}
VIEWER = {"id": 4, "full_name": "Người xem test", "role": "viewer"}


def ask(text, user=ANALYST, **kw):
    return assistant.chat(text, user, **kw)["message"]


@pytest.mark.parametrize("text,intent", [
    ("Khu vực nào có điều kiện thuận lợi nhất tuần này?", "ENVIRONMENTAL_RISK"),
    ("vi sao ESS cua KV-C cao", "EXPLAIN_SCORE"),
    ("Những khu vực nào cần ưu tiên kiểm tra?", "PRIORITY_INSPECTION"),
    ("Lượng mưa 7 ngày qua ở KV-K", "WEATHER_ANALYSIS"),
    ("Điểm nước đọng tập trung ở đâu?", "SPATIAL_ANALYSIS"),
    ("Kết quả khảo sát bọ gậy ở KV-E", "VECTOR_ANALYSIS"),
    ("Khu vực nào thay đổi nhanh nhất so với kỳ trước?", "TREND_ANALYSIS"),
    ("Có cảnh báo nào đang chờ duyệt?", "ALERT_QUERY"),
    ("Tạo báo cáo tuần", "REPORT_GENERATION"),
    ("Chạy phân tích cho KV-A và KV-B", "RUN_WORKFLOW"),
    ("Bạn làm được gì?", "GENERAL_QUESTION"),
    ("Mùa này khu vực nào thuận lợi?", "ENVIRONMENTAL_RISK"),  # "mùa" không bị nhầm thành "mưa"
])
def test_intent_rules(text, intent):
    assert llm.rule_chat_intent(text) == intent


def test_scope_extraction():
    areas = [{"id": i, "code": f"KV-{c}"} for i, c in enumerate("ABC", start=1)]
    assert assistant.extract_areas("so sánh KV-A với khu vực C", areas) == ([1, 3], [])
    assert assistant.extract_areas("khu vực nào cao nhất", areas) == ([], [])
    assert assistant.extract_areas("KV-Z thì sao", areas) == ([], ["KV-Z"])
    assert assistant.extract_days("14 ngày gần đây") == 14
    assert assistant.extract_days("2 tuần qua") == 14
    assert assistant.extract_days("tháng này") == 30


def test_answer_is_grounded_and_read_only():
    before = db.query_one("SELECT COUNT(*) AS n FROM analysis_runs")["n"]
    msg = ask("Những khu vực nào cần ưu tiên kiểm tra?")
    after = db.query_one("SELECT COUNT(*) AS n FROM analysis_runs")["n"]
    assert after == before, "trợ lý không được ghi kết quả phân tích"
    assert msg["intent"] == "PRIORITY_INSPECTION"
    assert [c["agent"] for c in msg["tool_calls"]] == ["Environmental Analysis Agent", "Geospatial Agent", "Risk & Alert Agent"]
    assert all(c["passed"] for c in msg["verification"])
    assert msg["scoring_version"] and msg["sources"]
    # Mọi con số trong câu trả lời đều nằm trong dữ kiện đã tính
    assert llm.check_grounded(msg["content"], msg["facts"]) is None
    assert msg["table"]["rows"][0]["pis"] >= msg["table"]["rows"][-1]["pis"]


def test_explain_named_area_and_missing_data():
    msg = ask("Vì sao ESS của KV-D như vậy?")
    assert msg["scope"]["area_codes"] == ["KV-D"]
    assert "Độ ẩm" in " ".join(msg["limitations"]) or "độ ẩm" in " ".join(msg["limitations"]).lower()
    assert any(r["value"] == "Thiếu" for r in msg["table"]["rows"])


def test_survey_answer_does_not_treat_not_surveyed_as_absence():
    msg = ask("Kết quả khảo sát muỗi ở KV-E và KV-J")
    assert msg["intent"] == "VECTOR_ANALYSIS"
    assert any("KHÔNG có nghĩa là không có véc-tơ" in l for l in msg["limitations"])


def test_out_of_scope_question_gets_guardrail():
    msg = ask("Dự đoán số ca bệnh tuần tới")
    assert msg["guardrail_note"]
    assert "không chẩn đoán" in msg["content"].lower() or "không chẩn đoán" in msg["guardrail_note"].lower()


def test_run_workflow_requires_confirmation_and_permission():
    tasks_before = db.query_one("SELECT COUNT(*) AS n FROM tasks")["n"]
    msg = ask("Chạy phân tích cho KV-A và KV-B 14 ngày")
    assert db.query_one("SELECT COUNT(*) AS n FROM tasks")["n"] == tasks_before, "không được tự tạo nhiệm vụ"
    assert msg["action"]["type"] == "create_task"
    assert msg["action"]["params"]["area_ids"] == [1, 2]
    viewer_msg = ask("Chạy phân tích cho KV-A", user=VIEWER)
    assert viewer_msg["action"] is None


def test_conversation_belongs_to_user():
    first = assistant.chat("Có cảnh báo nào?", ANALYST)
    conv = first["conversation_id"]
    assert len(assistant.history(conv, ANALYST)["messages"]) == 2
    with pytest.raises(Exception):
        assistant.history(conv, VIEWER)


def test_tool_policy_blocks_wrong_agent_and_writes():
    runner = ToolRunner("POLICY-TEST", "POLICY-TEST", read_only=True, backoff=0)
    with pytest.raises(ToolError) as exc:
        runner.call("Data Agent", "create_alert_proposals", results=[], task_id="X", user_name="x")
    assert exc.value.code == "TOOL_NOT_ALLOWED"
    with pytest.raises(ToolError) as exc:
        runner.call("Risk & Alert Agent", "create_alert_proposals", results=[], task_id="X", user_name="x")
    assert exc.value.code == "WRITE_NOT_ALLOWED"
    assert db.query_one("SELECT COUNT(*) AS n FROM tool_calls WHERE task_id='POLICY-TEST' AND status='denied'")["n"] == 2


def test_workflow_records_verification():
    task = orchestrator.create_task("Phân tích điều kiện môi trường KV-C", {
        "area_ids": [3, 4], "start": "2026-11-06", "end": "2026-11-12", "species": "aedes",
        "sources": ["weather", "water", "survey"]}, ANALYST, is_test=True)
    orchestrator.run_task(task["id"])
    done = orchestrator.get_task(task["id"])
    checks = done["result"]["verification"]
    assert {c["key"] for c in checks} >= {"areas", "period", "version", "sources", "human_approval"}
    assert all(c["passed"] for c in checks)


def test_verification_catches_wrong_period():
    task = orchestrator.create_task("Kiểm tra xác minh", {
        "area_ids": [3], "start": "2026-11-06", "end": "2026-11-12", "species": "aedes",
        "sources": ["weather", "water", "survey"]}, ANALYST, is_test=True)
    orchestrator.run_task(task["id"])
    run_id = orchestrator.get_task(task["id"])["result"]["run_ids"][0]
    db.execute("UPDATE analysis_runs SET start_date='2026-01-01' WHERE id=?", (run_id,))
    checks = orchestrator.verify_results(task["id"], {"area_ids": [3], "start": "2026-11-06", "end": "2026-11-12"},
                                         [{"run_id": run_id, "area_id": 3}], [])
    assert not next(c for c in checks if c["key"] == "period")["passed"]


# --- LLM thật (OpenAI-compatible) qua máy chủ giả -------------------------------
class FakeLLM(BaseHTTPRequestHandler):
    replies: list = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers["Content-Length"])
        FakeLLM.last_auth = self.headers.get("Authorization")
        FakeLLM.last_body = json.loads(self.rfile.read(length))
        reply = FakeLLM.replies.pop(0) if FakeLLM.replies else (500, "")
        status, content = reply
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if status == 200:
            self.wfile.write(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_llm(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(config, "LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(config, "LLM_API_KEY", "sk-test-secret")
    monkeypatch.setattr(config, "LLM_TIMEOUT", 3)
    FakeLLM.replies = []
    yield FakeLLM
    server.shutdown()


def test_real_llm_used_and_validated(fake_llm):
    fake_llm.replies = [(200, '{"intent": "ALERT_QUERY", "area_codes": ["KV-C", "KV-ZZ"], "days": 9999}'), (200, "Hiện có dữ liệu.")]
    msg = ask("cho tôi xem tình hình")
    assert msg["intent"] == "ALERT_QUERY"
    assert msg["scope"]["area_codes"] == ["KV-C"], "mã khu vực lạ do LLM trả về phải bị loại"
    assert msg["scope"]["days"] == 7, "số ngày ngoài phạm vi phải bị bỏ"
    assert "fake-model" in msg["intent_method"]
    assert fake_llm.last_auth == "Bearer sk-test-secret"
    stored = json.dumps(db.query("SELECT * FROM llm_calls"), ensure_ascii=False) + json.dumps(db.query("SELECT * FROM agent_messages"), ensure_ascii=False)
    assert "sk-test-secret" not in stored, "khóa API không được lưu"


def test_llm_bad_intent_and_outage_fall_back(fake_llm):
    fake_llm.replies = [(200, '{"intent": "DELETE_ALL_DATA"}')]
    msg = ask("Những khu vực nào cần ưu tiên kiểm tra?")
    assert msg["intent"] == "PRIORITY_INSPECTION" and "dự phòng" in msg["intent_method"]
    assert "dự phòng" in msg["answer_generated_by"]  # máy chủ hết câu trả lời → 500 → mẫu câu


def test_llm_summary_with_invented_number_is_rejected(fake_llm):
    fake_llm.replies = [(200, '{"intent": "PRIORITY_INSPECTION", "area_codes": [], "days": null}'),
                        (200, "KV-A có PIS 99.9 và chắc chắn sắp bùng phát dịch.")]
    msg = ask("Những khu vực nào cần ưu tiên kiểm tra?")
    assert "99.9" not in msg["content"]
    assert "bị loại" in msg["answer_generated_by"]
    assert db.query_one("SELECT status FROM llm_calls ORDER BY id DESC LIMIT 1")["status"] == "rejected"


def test_llm_grounded_summary_accepted(fake_llm):
    fake_llm.replies = [(200, '{"intent": "ALERT_QUERY", "area_codes": [], "days": null}')]
    facts_holder = {}
    original = llm.OpenAICompatLLM.summarize

    def spy(self, facts):
        facts_holder["facts"] = facts
        fake_llm.replies.append((200, facts[0]))  # LLM "diễn đạt" đúng dữ kiện
        return original(self, facts)

    llm.OpenAICompatLLM.summarize = spy
    try:
        msg = ask("Có cảnh báo nào?")
    finally:
        llm.OpenAICompatLLM.summarize = original
    assert msg["content"] == facts_holder["facts"][0]
    assert "fake-model" in msg["answer_generated_by"]


def test_misconfigured_provider_falls_back(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    status = llm.status()
    assert status["llm_mode"] == "simulated" and "VW_LLM_MODEL" in status["llm_warning"]
