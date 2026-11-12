"""Trợ lý AI Agent (VW-F11): hỏi đáp bằng ngôn ngữ tự nhiên trên dữ liệu của hệ thống.

Quy trình theo đặc tả: tiếp nhận → xác định ý định → xác định khu vực/thời gian → kiểm tra quyền → chọn Agent/tool
(định tuyến động) → truy xuất/phân tích → xác minh → tổng hợp và trả lời.

Nguyên tắc:
- Chỉ dùng công cụ CHỈ ĐỌC (ToolRunner read_only=True): trợ lý không ghi dữ liệu, không tạo/duyệt cảnh báo.
  Việc chạy workflow chỉ được ĐỀ XUẤT; người dùng có quyền phải bấm xác nhận.
- Mọi con số trong câu trả lời lấy từ kết quả công cụ (scoring service, CSDL). LLM (nếu bật) chỉ diễn đạt lại
  và bị kiểm tra đối chiếu số liệu; không đạt thì dùng mẫu câu xác định.
- Luôn nêu kỳ dữ liệu, nguồn, phiên bản công thức và giới hạn; không kết luận dịch bệnh.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from fastapi import HTTPException

from .. import db
from ..security import has_permission
from ..services import geo, scoring
from ..services.features import DataSnapshot
from .llm import CHAT_INTENTS, find_out_of_scope, get_llm, guardrail_note, normalize
from .orchestrator import MAX_WINDOW_DAYS
from .tools import ToolError, ToolRunner

DEFAULT_DAYS = 7
MAX_MESSAGE = 1000
DATA, ENV, GEO, RISK = "Data Agent", "Environmental Analysis Agent", "Geospatial Agent", "Risk & Alert Agent"
SPECIES = "aedes"

SUGGESTIONS = [
    "Khu vực nào có điều kiện môi trường thuận lợi nhất tuần này?",
    "Vì sao ESS của KV-C cao?",
    "Những khu vực nào cần ưu tiên kiểm tra?",
    "Lượng mưa 7 ngày qua ở KV-K thế nào?",
    "Điểm nước đọng tập trung ở đâu?",
    "Khu vực nào thay đổi nhanh nhất so với kỳ trước?",
    "Có cảnh báo nào đang chờ duyệt?",
    "Chạy phân tích cho KV-A và KV-B",
]

LIMIT_SCORE = ("ESS/PIS là điểm theo quy tắc minh họa (chưa được chuyên gia xác nhận), phản ánh mức thuận lợi của điều kiện "
               "môi trường — không phải xác suất có véc-tơ, mắc bệnh hay có dịch.")
LIMIT_SAMPLE = "Dữ liệu trong hệ thống là dữ liệu mẫu/giả lập."


def vn(iso: str) -> str:
    return "/".join(reversed(iso.split("-")))


def fmt(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{round(value, digits):g}"


# ---------------------------------------------------------------------------
# Trích phạm vi
# ---------------------------------------------------------------------------
_AREA_REF = re.compile(r"(?<![a-z0-9])(?:kv|khu vuc)[\s\-]*([a-z0-9])(?![a-z0-9])")


def extract_areas(message: str, areas: list[dict]) -> tuple[list[int], list[str]]:
    by_letter = {a["code"].split("-")[-1].lower(): a for a in areas}
    found, unknown = [], []
    for letter in _AREA_REF.findall(normalize(message)):
        area = by_letter.get(letter)
        if area and area["id"] not in found:
            found.append(area["id"])
        elif not area and f"KV-{letter.upper()}" not in unknown:
            unknown.append(f"KV-{letter.upper()}")
    return found, unknown


def extract_days(message: str) -> int | None:
    text = normalize(message)
    m = re.search(r"(\d+)\s*ngay", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*tuan", text)
    if m:
        return int(m.group(1)) * 7
    if any(k in text for k in ("thang nay", "thang qua", "1 thang", "mot thang", "30 ngay")):
        return 30
    if any(k in text for k in ("tuan nay", "tuan qua", "mot tuan")):
        return 7
    if any(k in text for k in ("hom nay", "hom qua")):
        return 1
    return None


# ---------------------------------------------------------------------------
# Phiên làm việc của một câu hỏi
# ---------------------------------------------------------------------------
class Turn:
    def __init__(self, message: str, user: dict, scope_area_ids: list[int], start: str, end: str, ref: str):
        self.message, self.user, self.area_ids, self.start, self.end, self.ref = message, user, scope_area_ids, start, end, ref
        self.runner = ToolRunner(ref, ref, read_only=True, backoff=0)
        self.runner.step_key = "assistant"
        self.areas = {a["id"]: a for a in geo.load_areas()}
        self.facts: list[str] = []
        self.limitations: list[str] = [LIMIT_SAMPLE]
        self.table: dict | None = None
        self.links: list[dict] = []
        self.action: dict | None = None
        self.sources: set[str] = set()
        self.uses_scoring = False

    def tool(self, agent: str, name: str, **kwargs) -> dict:
        out = self.runner.call(agent, name, **kwargs)
        self.sources.update(out.get("sources") or [])
        return out

    def period_fact(self) -> str:
        days = (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days + 1
        return f"Kỳ dữ liệu: {vn(self.start)} → {vn(self.end)} ({days} ngày), {len(self.area_ids)} khu vực."

    def code(self, area_id: int) -> str:
        return self.areas[area_id]["code"]

    def scores(self) -> list[dict]:
        out = self.tool(ENV, "get_environmental_score", area_ids=self.area_ids, start=self.start, end=self.end, species=SPECIES)
        self.uses_scoring = True
        for r in out["results"]:
            for c in r["components"]:
                if not c["missing"] and c.get("source"):
                    self.sources.update(s.strip() for s in c["source"].split(";"))
        return out["results"]


# ---------------------------------------------------------------------------
# Bộ xử lý theo ý định (định tuyến động)
# ---------------------------------------------------------------------------
def _score_rows(results: list[dict]) -> list[dict]:
    return [{"area": r["area_code"], "ess": r["ess"], "ess_class": r["ess_class"]["label"] if r["ess_class"] else "Không đủ dữ liệu",
             "pis": r["pis"], "completeness": round(r["completeness"] * 100), "missing": ", ".join(m["label"] for m in r["missing"]) or "—"}
            for r in results]


SCORE_COLUMNS = [{"key": "area", "label": "Khu vực"}, {"key": "ess", "label": "ESS", "num": True},
                 {"key": "ess_class", "label": "Nhóm ESS"}, {"key": "pis", "label": "PIS", "num": True},
                 {"key": "completeness", "label": "Đủ dữ liệu (%)", "num": True}, {"key": "missing", "label": "Thiếu"}]


def _not_scored_fact(t: Turn, results: list[dict]) -> None:
    missing = [r["area_code"] for r in results if r["ess"] is None]
    if missing:
        t.facts.append(f"Không đủ dữ liệu để tính ESS cho: {', '.join(missing)} — hệ thống để trống điểm, không suy đoán.")


def h_environmental(t: Turn) -> None:
    results = t.scores()
    scored = sorted((r for r in results if r["ess"] is not None), key=lambda r: r["ess"], reverse=True)
    t.facts.append(t.period_fact())
    if scored:
        top = scored[:3]
        t.facts.append("ESS cao nhất: " + "; ".join(f"{r['area_code']} {fmt(r['ess'])} ({r['ess_class']['label']})" for r in top) + ".")
        if len(scored) > 3:
            low = scored[-1]
            t.facts.append(f"ESS thấp nhất: {low['area_code']} {fmt(low['ess'])} ({low['ess_class']['label']}).")
    _not_scored_fact(t, results)
    t.table = {"title": "ESS/PIS theo khu vực (sắp xếp theo ESS)", "columns": SCORE_COLUMNS,
               "rows": _score_rows(scored + [r for r in results if r["ess"] is None])}
    t.links += [{"label": "Xem trên bản đồ", "to": "/map"}, {"label": "Phân tích chi tiết", "to": f"/analysis?area={scored[0]['area_id'] if scored else t.area_ids[0]}"}]
    t.limitations.append(LIMIT_SCORE)


def h_explain(t: Turn, explicit: bool) -> None:
    results = t.scores()
    t.facts.append(t.period_fact() if len(t.area_ids) > 1 else
                   f"Kỳ dữ liệu: {vn(t.start)} → {vn(t.end)}, khu vực {t.code(t.area_ids[0])}.")
    scored = [r for r in results if r["ess"] is not None]
    if not scored:
        _not_scored_fact(t, results)
        t.facts.append(results[0]["explanation"]["summary"][0])
        return
    target = scored[0] if explicit and len(t.area_ids) == 1 else max(scored, key=lambda r: r["ess"])
    if not (explicit and len(t.area_ids) == 1):
        t.facts.append(f"Câu hỏi không nêu một khu vực cụ thể nên giải thích khu vực có ESS cao nhất là {target['area_code']}.")
    t.facts.append(f"{target['area_code']}: " + " ".join(target["explanation"]["summary"]))
    t.limitations += [l for l in target["explanation"]["limitations"] if l not in t.limitations]
    t.table = {"title": f"Thành phần ESS của {target['area_code']}",
               "columns": [{"key": "factor", "label": "Yếu tố"}, {"key": "value", "label": "Giá trị"},
                           {"key": "score", "label": "Điểm", "num": True}, {"key": "weight", "label": "Trọng số hiệu dụng", "num": True},
                           {"key": "contribution", "label": "Đóng góp", "num": True}],
               "rows": [{"factor": c["label"], "value": "Thiếu" if c["missing"] else f"{fmt(c['value'], 2)} {c['unit']}",
                         "score": c.get("score"), "weight": c.get("effective_weight"), "contribution": c.get("contribution")}
                        for c in target["components"]]}
    t.links.append({"label": f"Mở phân tích {target['area_code']}", "to": f"/analysis?area={target['area_id']}"})
    t.limitations.append(LIMIT_SCORE)


def h_priority(t: Turn) -> None:
    results = t.scores()
    spatial = t.tool(GEO, "analyze_spatial_distribution", area_ids=t.area_ids, end=t.end)
    ranking = t.tool(RISK, "rank_priority_locations", results=[{**r, "run_id": None} for r in results])["ranking"]
    t.facts.append(t.period_fact())
    water = {x["area_id"]: x["active"] for x in spatial["per_area"]}
    if ranking:
        top = [r for r in ranking if r["pis"] >= 50][:5] or ranking[:3]
        t.facts.append("Khu vực nên ưu tiên kiểm tra theo PIS: " + "; ".join(
            f"{r['area_code']} PIS {fmt(r['pis'])} ({r['pis_class']}, {water.get(r['area_id'], 0)} điểm nước đọng đang tồn tại)" for r in top) + ".")
        n_inspect = sum(1 for r in ranking if r["pis"] >= 50)
        t.facts.append(f"{n_inspect}/{len(ranking)} khu vực có PIS từ 50 trở lên (mức Cần kiểm tra hoặc cao hơn).")
    _not_scored_fact(t, results)
    t.table = {"title": "Xếp hạng ưu tiên kiểm tra (PIS)",
               "columns": [{"key": "rank", "label": "#", "num": True}, {"key": "area", "label": "Khu vực"},
                           {"key": "pis", "label": "PIS", "num": True}, {"key": "level", "label": "Mức"},
                           {"key": "ess", "label": "ESS", "num": True}, {"key": "water", "label": "Nước đọng đang tồn tại", "num": True}],
               "rows": [{"rank": r["rank"], "area": r["area_code"], "pis": r["pis"], "level": r["pis_class"], "ess": r["ess"],
                         "water": water.get(r["area_id"], 0)} for r in ranking]}
    t.links += [{"label": "Bản đồ ưu tiên", "to": "/map"}, {"label": "Cảnh báo & phê duyệt", "to": "/alerts"}]
    t.limitations += [LIMIT_SCORE, "Đây là thứ tự gợi ý để lập kế hoạch kiểm tra; quyết định cuối cùng thuộc cán bộ có thẩm quyền."]


def h_weather(t: Turn) -> None:
    out = t.tool(DATA, "summarize_weather", area_ids=t.area_ids, start=t.start, end=t.end)
    t.facts.append(t.period_fact())
    per = out["per_area"]
    detail = per if len(per) <= 4 else sorted([p for p in per if p["rain_total"] is not None], key=lambda p: p["rain_total"], reverse=True)[:3]
    if len(per) > 4 and detail:
        t.facts.append("Mưa tích lũy nhiều nhất: " + "; ".join(f"{p['area_code']} {fmt(p['rain_total'])} mm" for p in detail) + ".")
    else:
        for p in detail:
            def cover(n):
                return "" if n == p["days"] else f" (chỉ {n}/{p['days']} ngày có số liệu)"
            parts = [f"mưa tích lũy {fmt(p['rain_total'])} mm{cover(p['rain_days'])}" if p["rain_total"] is not None else "không có số liệu mưa",
                     f"nhiệt độ trung bình {fmt(p['temp_mean'])} °C{cover(p['temp_days'])}" if p["temp_mean"] is not None else "không có số liệu nhiệt độ",
                     f"độ ẩm trung bình {fmt(p['humidity_mean'])}%{cover(p['humidity_days'])}" if p["humidity_mean"] is not None else "không có số liệu độ ẩm"]
            t.facts.append(f"{p['area_code']}: " + ", ".join(parts) + ".")
    gaps = [p["area_code"] for p in per if min(p["rain_days"], p["temp_days"], p["humidity_days"]) < p["days"]]
    if gaps:
        t.facts.append(f"Có ngày thiếu số liệu ở: {', '.join(gaps)} — ngày thiếu không được tính là 0.")
    t.table = {"title": "Tổng hợp thời tiết (giá trị quan trắc trong dữ liệu, không nội suy)",
               "columns": [{"key": "area", "label": "Khu vực"}, {"key": "rain", "label": "Mưa (mm)", "num": True},
                           {"key": "temp", "label": "Nhiệt độ TB (°C)", "num": True}, {"key": "hum", "label": "Độ ẩm TB (%)", "num": True},
                           {"key": "cover", "label": "Ngày có số liệu (mưa/nhiệt/ẩm)"}],
               "rows": [{"area": p["area_code"], "rain": p["rain_total"], "temp": p["temp_mean"], "hum": p["humidity_mean"],
                         "cover": f"{p['rain_days']}/{p['temp_days']}/{p['humidity_days']} trên {p['days']}"} for p in per]}
    t.links.append({"label": "Dữ liệu thời tiết", "to": "/data"})


def h_spatial(t: Turn) -> None:
    out = t.tool(GEO, "analyze_spatial_distribution", area_ids=t.area_ids, end=t.end)
    per = out["per_area"]
    total = sum(p["active"] for p in per)
    t.facts.append(f"Tính đến {vn(t.end)}: {total} điểm nước đọng đang tồn tại trên {len(per)} khu vực.")
    if per and total:
        t.facts.append("Tập trung nhiều nhất: " + "; ".join(f"{p['area_code']} {p['active']} điểm" for p in per[:3] if p["active"]) + ".")
    outside = sum(p["active"] - p["inside_polygon"] for p in per)
    if outside:
        t.facts.append(f"{outside} điểm đang tồn tại nằm ngoài ranh giới khu vực được gán — cần kiểm tra lại tọa độ.")
    t.table = {"title": "Phân bố điểm nước đọng đang tồn tại",
               "columns": [{"key": "area", "label": "Khu vực"}, {"key": "active", "label": "Đang tồn tại", "num": True},
                           {"key": "recorded", "label": "Đã ghi nhận", "num": True}, {"key": "types", "label": "Theo loại"}],
               "rows": [{"area": p["area_code"], "active": p["active"], "recorded": p["total_recorded"],
                         "types": ", ".join(f"{k}: {v}" for k, v in p["by_type"].items()) or "—"} for p in per]}
    t.links.append({"label": "Xem điểm nước đọng trên bản đồ", "to": "/map"})


def h_survey(t: Turn) -> None:
    out = t.tool(DATA, "summarize_surveys", area_ids=t.area_ids, start=t.start, end=t.end, species=SPECIES)
    per = out["per_area"]
    t.facts.append(t.period_fact())
    valid = sum(p["valid"] for p in per)
    positive = sum(p["positive"] for p in per)
    t.facts.append(f"{valid} lượt khảo sát hợp lệ, {positive} lượt có ghi nhận ấu trùng/muỗi trưởng thành (Aedes).")
    pending = [p["area_code"] for p in per if p["not_surveyed"]]
    none = [p["area_code"] for p in per if p["records"] == 0]
    if pending:
        t.facts.append(f"Có lượt “chưa khảo sát” ở: {', '.join(pending)}.")
    if none:
        t.facts.append(f"Không có bản ghi khảo sát trong kỳ ở: {', '.join(none)}.")
    t.limitations.append("“Chưa khảo sát” hoặc không có bản ghi KHÔNG có nghĩa là không có véc-tơ.")
    t.table = {"title": "Khảo sát thực địa trong kỳ",
               "columns": [{"key": "area", "label": "Khu vực"}, {"key": "valid", "label": "Hợp lệ", "num": True},
                           {"key": "positive", "label": "Có ghi nhận", "num": True}, {"key": "pending", "label": "Chưa khảo sát", "num": True},
                           {"key": "ratio", "label": "Tỷ lệ ghi nhận", "num": True}],
               "rows": [{"area": p["area_code"], "valid": p["valid"], "positive": p["positive"], "pending": p["not_surveyed"],
                         "ratio": p["positive_ratio"]} for p in per]}
    t.links.append({"label": "Dữ liệu khảo sát", "to": "/data"})


def h_trend(t: Turn) -> None:
    results = t.scores()
    t.facts.append(t.period_fact())
    rows = []
    for r in results:
        prev = r["previous_period"]
        delta = round(r["ess"] - prev["ess"], 1) if r["ess"] is not None and prev["ess"] is not None else None
        rows.append({"area": r["area_code"], "prev": prev["ess"], "now": r["ess"], "delta": delta})
    comparable = sorted([x for x in rows if x["delta"] is not None], key=lambda x: x["delta"], reverse=True)
    if comparable:
        prev = results[0]["previous_period"]
        t.facts.append(f"So sánh với kỳ trước liền kề ({vn(prev['start'])} → {vn(prev['end'])}).")
        up = [x for x in comparable if x["delta"] > 0][:3]
        if up:
            t.facts.append("ESS tăng nhiều nhất: " + "; ".join(f"{x['area']} {fmt(x['prev'])} → {fmt(x['now'])} (+{fmt(x['delta'])})" for x in up) + ".")
        down = [x for x in comparable if x["delta"] < 0]
        if down:
            d = down[-1]
            t.facts.append(f"Giảm nhiều nhất: {d['area']} {fmt(d['prev'])} → {fmt(d['now'])} ({fmt(d['delta'])}).")
    no_cmp = [x["area"] for x in rows if x["delta"] is None]
    if no_cmp:
        t.facts.append(f"Không so sánh được (một trong hai kỳ không đủ dữ liệu): {', '.join(no_cmp)}.")
    t.limitations += [LIMIT_SCORE, "Đây là so sánh hai kỳ đã quan sát, không phải dự báo xu hướng tương lai; thay đổi không chứng minh quan hệ nhân quả."]
    t.table = {"title": "Thay đổi ESS so với kỳ trước liền kề",
               "columns": [{"key": "area", "label": "Khu vực"}, {"key": "prev", "label": "ESS kỳ trước", "num": True},
                           {"key": "now", "label": "ESS kỳ này", "num": True}, {"key": "delta", "label": "Chênh lệch", "num": True}],
               "rows": comparable + [x for x in rows if x["delta"] is None]}
    t.links.append({"label": "Biểu đồ xu hướng (Dashboard)", "to": "/"})


def h_alerts(t: Turn) -> None:
    text = normalize(t.message)
    status = "pending" if "cho duyet" in text else None
    out = t.tool(RISK, "get_alerts", area_ids=t.area_ids, status=status)
    items = out["alerts"]
    counts: dict[str, int] = {}
    for a in items:
        counts[a["status_label"]] = counts.get(a["status_label"], 0) + 1
    scope = "đang chờ duyệt" if status else "trong hệ thống"
    t.facts.append(f"Có {len(items)} cảnh báo/đề xuất {scope} thuộc {len(t.area_ids)} khu vực được hỏi." +
                   ("" if status or not counts else " Theo trạng thái: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + "."))
    pending = [a for a in items if a["status"] in ("pending", "needs_revision")]
    if pending:
        t.facts.append("Cần quyết định: " + "; ".join(f"{a['code']} ({a['area_code']}, mức {a['severity_label'].lower()}, PIS {fmt(a['pis'])})" for a in pending[:5]) + ".")
    t.limitations.append("Trợ lý không phê duyệt hay từ chối đề xuất; việc đó do cán bộ có thẩm quyền thực hiện ở trang Cảnh báo.")
    t.table = {"title": "Cảnh báo và đề xuất",
               "columns": [{"key": "code", "label": "Mã"}, {"key": "area", "label": "Khu vực"}, {"key": "type", "label": "Loại"},
                           {"key": "severity", "label": "Mức"}, {"key": "status", "label": "Trạng thái"}, {"key": "pis", "label": "PIS", "num": True}],
               "rows": [{"code": a["code"], "area": a["area_code"], "type": a["type_label"], "severity": a["severity_label"],
                         "status": a["status_label"], "pis": a["pis"]} for a in items[:30]]}
    t.links.append({"label": "Mở trang Cảnh báo & phê duyệt", "to": "/alerts" + ("?status=pending" if status else "")})


def h_report(t: Turn) -> None:
    results = t.scores()
    scored = [r for r in results if r["ess"] is not None]
    t.facts.append(t.period_fact())
    if scored:
        avg = sum(r["ess"] for r in scored) / len(scored)
        t.facts.append(f"ESS trung bình {fmt(avg)} trên {len(scored)} khu vực đủ dữ liệu; "
                       f"{sum(1 for r in scored if r['pis'] is not None and r['pis'] >= 50)} khu vực có PIS từ 50 trở lên.")
    _not_scored_fact(t, results)
    t.facts.append("Báo cáo đầy đủ (dữ liệu, bản đồ, cảnh báo, khuyến nghị, giới hạn, nguồn) được tạo ở trang Báo cáo; có thể xuất Excel hoặc in PDF.")
    t.links.append({"label": "Mở trang Báo cáo", "to": "/reports"})
    t.limitations.append(LIMIT_SCORE)


def h_run(t: Turn) -> None:
    allowed = has_permission(t.user, "task.create")
    names = ", ".join(t.code(a) for a in t.area_ids)
    t.facts.append(f"Đề xuất tạo nhiệm vụ workflow đầy đủ cho {len(t.area_ids)} khu vực ({names}), kỳ {vn(t.start)} → {vn(t.end)}, loài Aedes.")
    t.facts.append("Workflow gồm: lấy dữ liệu, kiểm tra dữ liệu, phân tích môi trường, phân tích địa lý, tạo đề xuất và chờ người duyệt.")
    if allowed:
        t.facts.append("Nhiệm vụ chỉ bắt đầu khi bạn bấm xác nhận.")
        t.action = {"type": "create_task", "label": "Xác nhận tạo nhiệm vụ",
                    "params": {"objective": t.message[:300], "area_ids": t.area_ids, "start": t.start, "end": t.end,
                               "species": SPECIES, "sources": ["weather", "water", "survey"], "notes": f"Tạo từ Trợ lý ({t.ref})"}}
    else:
        t.facts.append("Tài khoản của bạn không có quyền tạo nhiệm vụ Agent; hãy nhờ chuyên viên phân tích hoặc cán bộ giám sát.")


def h_general(t: Turn) -> None:
    t.facts.append("Tôi là Trợ lý của VectorWatch AI. Tôi trả lời dựa trên dữ liệu và scoring service của hệ thống: mức thuận lợi môi trường (ESS), "
                   "khu vực ưu tiên kiểm tra (PIS), lý do điểm cao/thấp, thời tiết, điểm nước đọng, khảo sát, thay đổi so với kỳ trước và cảnh báo hiện có.")
    t.facts.append("Bạn có thể nêu khu vực (ví dụ KV-C) và số ngày (ví dụ 14 ngày). Tôi cũng có thể đề xuất chạy workflow phân tích đầy đủ để bạn xác nhận.")
    t.facts.append("Tôi không chẩn đoán bệnh, không dự đoán ca bệnh hay kết luận có dịch.")


# ---------------------------------------------------------------------------
# Xác minh câu trả lời
# ---------------------------------------------------------------------------
def verify(t: Turn, summary_by: str, answer: str) -> list[dict]:
    checks = [{"label": "Phạm vi hợp lệ", "passed": all(a in t.areas for a in t.area_ids) and bool(t.area_ids),
               "detail": f"{len(t.area_ids)} khu vực, kỳ {vn(t.start)} → {vn(t.end)}"}]
    calls = db.query("SELECT tool, status FROM tool_calls WHERE task_id=?", (t.ref,))
    writes = [c["tool"] for c in calls if c["tool"] in ("compute_environmental_score", "create_alert_proposals")]
    checks.append({"label": "Chỉ dùng công cụ chỉ đọc", "passed": not writes,
                   "detail": f"{len(calls)} lần gọi công cụ, không ghi dữ liệu" if not writes else f"có công cụ ghi: {writes}"})
    failed = [c["tool"] for c in calls if c["status"] not in ("success",)]
    checks.append({"label": "Công cụ chạy thành công", "passed": not failed,
                   "detail": "mọi lần gọi đều thành công" if not failed else f"lỗi ở: {', '.join(failed)}"})
    if calls:
        checks.append({"label": "Có nguồn dữ liệu", "passed": bool(t.sources) or not t.uses_scoring,
                       "detail": "; ".join(sorted(t.sources)) or "câu trả lời không dùng số liệu quan trắc"})
    if t.uses_scoring:
        checks.append({"label": "Điểm do scoring service tính", "passed": True, "detail": f"scoring {scoring.SCORING_VERSION}"})
    checks.append({"label": "Số liệu trong câu trả lời lấy từ dữ kiện", "passed": True, "detail": summary_by})
    flagged = find_out_of_scope(answer) and not find_out_of_scope(" ".join(t.facts))
    checks.append({"label": "Không kết luận dịch bệnh", "passed": not flagged, "detail": "đạt" if not flagged else "phát hiện nội dung ngoài phạm vi"})
    return checks


# ---------------------------------------------------------------------------
# API chính
# ---------------------------------------------------------------------------
def _conversation(conversation_id: str | None, user: dict) -> str:
    if conversation_id:
        row = db.query_one("SELECT user_id FROM agent_messages WHERE conversation_id=? LIMIT 1", (conversation_id,))
        if row and row["user_id"] != user["id"]:
            raise HTTPException(403, "Cuộc trò chuyện này thuộc người dùng khác.")
        if row:
            return conversation_id
    return f"CONV-{uuid.uuid4().hex[:10].upper()}"


def chat(message: str, user: dict, conversation_id: str | None = None, context: dict | None = None) -> dict:
    message = (message or "").strip()
    if len(message) < 2:
        raise HTTPException(422, "Hãy nhập câu hỏi.")
    if len(message) > MAX_MESSAGE:
        raise HTTPException(422, f"Câu hỏi tối đa {MAX_MESSAGE} ký tự.")
    context = context or {}
    conv = _conversation(conversation_id, user)
    ref = f"MSG-{uuid.uuid4().hex[:10].upper()}"
    now = db.now_iso()
    db.execute("INSERT INTO agent_messages (conversation_id, user_id, role, content, payload, created_at) VALUES (?,?,?,?,?,?)",
               (conv, user["id"], "user", message, db.dumps({"ref": ref, "context": context}), now))

    areas = geo.load_areas()
    codes = [a["code"] for a in areas]
    trace = [{"step": "Tiếp nhận", "agent": "Orchestrator", "detail": f"Mã {ref}; nội dung người dùng được xử lý như dữ liệu, không như chỉ dẫn."}]

    llm = get_llm()
    llm.ref = ref
    understood = llm.understand(message, codes)
    intent = understood["intent"]
    flagged = find_out_of_scope(message)
    trace.append({"step": "Xác định ý định", "agent": "Orchestrator",
                  "detail": f"{intent} — {CHAT_INTENTS[intent]['label']} ({understood['method']})"})

    # --- Phạm vi: khu vực nêu trong câu > LLM gợi ý (đã kiểm tra) > bộ lọc giao diện > tất cả ----------
    by_code = {a["code"]: a["id"] for a in areas}
    mentioned, unknown = extract_areas(message, areas)
    scope_from = "câu hỏi"
    area_ids = mentioned or [by_code[c] for c in understood.get("area_codes") or []]
    if not area_ids:
        ctx_ids = [int(a) for a in context.get("area_ids") or [] if int(a) in by_code.values()]
        area_ids, scope_from = (ctx_ids, "bộ lọc khu vực") if ctx_ids else ([a["id"] for a in areas], "mặc định (toàn khu vực thí điểm)")
    elif not mentioned:
        scope_from = "LLM gợi ý (đã đối chiếu danh mục)"
    days_asked = extract_days(message) or understood.get("days") or context.get("days") or DEFAULT_DAYS
    days = max(1, min(int(days_asked), MAX_WINDOW_DAYS))
    latest = DataSnapshot().latest_weather_date()
    if not latest:
        raise HTTPException(409, "Chưa có dữ liệu thời tiết trong hệ thống nên chưa thể trả lời. Hãy nhập dữ liệu trước.")
    end = latest
    start = (date.fromisoformat(end) - timedelta(days=days - 1)).isoformat()
    trace.append({"step": "Xác định phạm vi", "agent": "Orchestrator",
                  "detail": f"{len(area_ids)} khu vực (theo {scope_from}); {days} ngày đến ngày dữ liệu mới nhất {vn(end)}"})
    trace.append({"step": "Kiểm tra quyền", "agent": "Orchestrator",
                  "detail": f"Vai trò {user['role']}: được tra cứu (chỉ đọc)" +
                            ("; được đề xuất tạo nhiệm vụ" if has_permission(user, "task.create") else "; không có quyền tạo nhiệm vụ")})
    agents = CHAT_INTENTS[intent]["agents"]
    trace.append({"step": "Định tuyến", "agent": "Orchestrator", "detail": " → ".join(agents)})

    t = Turn(message, user, area_ids, start, end, ref)
    if unknown:
        t.facts.append(f"Không tìm thấy khu vực {', '.join(unknown)} trong danh mục; các khu vực hiện có: {codes[0]} đến {codes[-1]}.")
    if days_asked != days:
        t.facts.append(f"Kỳ được giới hạn còn {days} ngày (tối đa {MAX_WINDOW_DAYS} ngày mỗi lần).")
    if flagged:
        t.facts.append(guardrail_note(flagged))
    handler = {
        "ENVIRONMENTAL_RISK": h_environmental, "PRIORITY_INSPECTION": h_priority, "WEATHER_ANALYSIS": h_weather,
        "SPATIAL_ANALYSIS": h_spatial, "VECTOR_ANALYSIS": h_survey, "TREND_ANALYSIS": h_trend, "ALERT_QUERY": h_alerts,
        "REPORT_GENERATION": h_report, "RUN_WORKFLOW": h_run, "GENERAL_QUESTION": h_general,
    }.get(intent)
    status = "ok"
    try:
        if intent == "EXPLAIN_SCORE":
            h_explain(t, explicit=bool(mentioned or understood.get("area_codes")))
        elif flagged and intent == "GENERAL_QUESTION":
            t.facts.append("Tôi có thể cho biết khu vực nào có điều kiện môi trường thuận lợi hoặc cần ưu tiên kiểm tra thực địa — hãy hỏi theo hướng đó.")
        else:
            handler(t)
    except ToolError as exc:
        status = "error"
        t.facts = [f"Không lấy được dữ liệu ({exc.code}): {exc.message} Tôi không đưa ra kết luận khi thiếu kết quả công cụ. Hãy thử lại sau."]
        t.table, t.action = None, None

    answer, summary_by = llm.summarize(t.facts)
    checks = verify(t, summary_by, answer)
    trace.append({"step": "Xác minh", "agent": "Orchestrator",
                  "detail": f"{sum(c['passed'] for c in checks)}/{len(checks)} kiểm tra đạt"})
    calls = db.query("SELECT agent, tool, status, duration_ms, error_code FROM tool_calls WHERE task_id=? ORDER BY id", (ref,))
    payload = {
        "ref": ref, "trace_id": ref, "status": status, "intent": intent, "intent_label": CHAT_INTENTS[intent]["label"],
        "intent_method": understood["method"], "agents": agents,
        "scope": {"area_codes": [t.code(a) for a in area_ids], "start": start, "end": end, "days": days, "from": scope_from},
        "facts": t.facts, "answer_generated_by": summary_by, "table": t.table, "links": t.links, "action": t.action,
        "sources": sorted(t.sources), "scoring_version": scoring.SCORING_VERSION if t.uses_scoring else None,
        "limitations": t.limitations, "verification": checks, "trace": trace, "tool_calls": calls,
        "guardrail_note": guardrail_note(flagged),
    }
    msg_id = db.execute("INSERT INTO agent_messages (conversation_id, user_id, role, content, payload, created_at) VALUES (?,?,?,?,?,?)",
                        (conv, user["id"], "assistant", answer, db.dumps(payload), db.now_iso()))
    return {"conversation_id": conv, "message": {"id": msg_id, "role": "assistant", "content": answer,
                                                 "created_at": db.now_iso(), **payload}}


def history(conversation_id: str, user: dict) -> dict:
    rows = db.query("SELECT * FROM agent_messages WHERE conversation_id=? ORDER BY id", (conversation_id,))
    if not rows:
        raise HTTPException(404, "Không tìm thấy cuộc trò chuyện.")
    if rows[0]["user_id"] != user["id"]:
        raise HTTPException(403, "Cuộc trò chuyện này thuộc người dùng khác.")
    return {"conversation_id": conversation_id,
            "messages": [{"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"],
                          **db.loads(r["payload"], {})} for r in rows]}


def conversations(user: dict) -> list[dict]:
    return db.query("""SELECT conversation_id, MIN(created_at) AS started_at, MAX(created_at) AS updated_at, COUNT(*) AS messages,
                              (SELECT content FROM agent_messages m2 WHERE m2.conversation_id=m.conversation_id AND role='user'
                               ORDER BY id LIMIT 1) AS title
                       FROM agent_messages m WHERE user_id=? GROUP BY conversation_id ORDER BY MAX(id) DESC LIMIT 20""", (user["id"],))
