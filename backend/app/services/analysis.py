"""Dịch vụ phân tích: ghép đặc trưng + scoring, lưu kết quả kèm phiên bản, tham số và đầu vào."""
from __future__ import annotations

from datetime import timedelta

from .. import db
from . import scoring
from .features import ALL_SOURCES, DataSnapshot, parse_date


def _strip(features: dict) -> dict:
    """Bỏ các bảng dữ liệu thô khỏi đặc trưng để trả về gọn."""
    return {k: v for k, v in features.items() if not k.endswith("_rows") and k != "_meta"}


def evaluate(snapshot: DataSnapshot, area_id: int, start: str, end: str, species: str = "aedes",
             sources: tuple[str, ...] = ALL_SOURCES, include_rows: bool = False) -> dict:
    """Tính ESS/PIS cho một khu vực và một kỳ. Không ghi CSDL."""
    feats = snapshot.features(area_id, start, end, species, sources)
    ess_result = scoring.compute_ess(feats, species)

    # Kỳ trước liền kề, cùng độ dài → ChangeScore
    d0, d1 = parse_date(start), parse_date(end)
    length = (d1 - d0).days + 1
    prev_end = (d0 - timedelta(days=1)).isoformat()
    prev_start = (d0 - timedelta(days=length)).isoformat()
    prev_feats = snapshot.features(area_id, prev_start, prev_end, species, sources)
    prev_ess = scoring.compute_ess(prev_feats, species)

    comp = {c["key"]: c for c in ess_result["components"]}
    water_score = comp.get("water", {}).get("score")
    survey_score = comp.get("survey", {}).get("score")
    change_score = scoring.compute_change_score(ess_result["ess"], prev_ess["ess"])
    pis_result = scoring.compute_pis(ess_result["ess"], water_score, survey_score, change_score)

    result = {
        "area_id": area_id,
        "species": species,
        "start_date": start,
        "end_date": end,
        "sources_used": list(sources),
        "status": ess_result["status"],
        "message": ess_result.get("message"),
        "ess": ess_result["ess"],
        "ess_class": ess_result["ess_class"],
        "pis": pis_result["pis"],
        "pis_class": pis_result["pis_class"],
        "completeness": ess_result["completeness"],
        "components": ess_result["components"],
        "missing": ess_result["missing"],
        "pis_components": pis_result["components"],
        "pis_message": pis_result.get("message"),
        "previous_period": {"start": prev_start, "end": prev_end, "ess": prev_ess["ess"], "status": prev_ess["status"]},
        "change_score": change_score,
        "features": _strip(feats),
        "scoring_version": scoring.SCORING_VERSION,
        "explanation": build_explanation(ess_result, pis_result, prev_ess),
    }
    if include_rows:
        result["inputs"] = {
            "weather": feats.get("weather_rows", []),
            "water_points": feats.get("water_rows", []),
            "surveys": feats.get("survey_rows", []),
        }
    return result


def build_explanation(ess_result: dict, pis_result: dict, prev_ess: dict) -> dict:
    """Giải thích sinh từ mẫu câu xác định (không phải LLM), chỉ dùng số liệu đã tính."""
    lines: list[str] = []
    if ess_result["ess"] is None:
        lines.append(ess_result.get("message") or "Không đủ dữ liệu để tính ESS.")
    else:
        cls = ess_result["ess_class"]
        lines.append(f"ESS = {ess_result['ess']:g}/100, nhóm “{cls['label']}” ({cls['meaning'].lower()}).")
        ranked = sorted((c for c in ess_result["components"] if not c["missing"]),
                        key=lambda c: c["contribution"], reverse=True)
        top = ", ".join(f"{c['label']} (+{c['contribution']:g})" for c in ranked[:3])
        lines.append(f"Yếu tố đóng góp lớn nhất: {top}.")
        low = [c for c in ranked if c["score"] < 40]
        if low:
            lines.append("Yếu tố kéo điểm xuống: " + ", ".join(f"{c['label']} ({c['score']:g}đ)" for c in low) + ".")
        if prev_ess["ess"] is not None:
            delta = ess_result["ess"] - prev_ess["ess"]
            trend = "tăng" if delta > 0 else "giảm" if delta < 0 else "không đổi"
            lines.append(f"So với kỳ trước liền kề (ESS {prev_ess['ess']:g}): {trend} {abs(delta):.1f} điểm.")
        else:
            lines.append("Không so sánh được với kỳ trước vì kỳ trước không đủ dữ liệu.")
    if pis_result["pis"] is not None:
        lines.append(f"PIS = {pis_result['pis']:g}/100, mức “{pis_result['pis_class']['label']}”.")
    limits = [f"Thiếu dữ liệu: {m['label']} — {m['reason']}" for m in ess_result["missing"]]
    if ess_result["missing"] and ess_result["ess"] is not None:
        limits.append("Trọng số đã được chia lại trên các thành phần có dữ liệu; độ tin cậy của điểm thấp hơn khi đủ dữ liệu.")
    limits.append("Điểm cao không có nghĩa chắc chắn có muỗi/ổ bọ gậy; cần xác minh thực địa.")
    return {"summary": lines, "limitations": limits, "generated_by": "Mẫu câu xác định (không dùng LLM)"}


def run_and_save(area_id: int, start: str, end: str, species: str, user_name: str,
                 sources: tuple[str, ...] = ALL_SOURCES, task_id: str | None = None,
                 snapshot: DataSnapshot | None = None) -> dict:
    snapshot = snapshot or DataSnapshot()
    result = evaluate(snapshot, area_id, start, end, species, sources, include_rows=True)
    result["params"] = scoring.public_config()
    created_at = db.now_iso()
    run_id = db.execute(
        """INSERT INTO analysis_runs (area_id, species, start_date, end_date, status, ess, ess_class, pis, pis_class,
               completeness, scoring_version, payload, created_at, created_by, task_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (area_id, species, start, end, result["status"], result["ess"],
         result["ess_class"]["key"] if result["ess_class"] else None, result["pis"],
         result["pis_class"]["key"] if result["pis_class"] else None, result["completeness"],
         result["scoring_version"], db.dumps(result), created_at, user_name, task_id),
    )
    result.update(run_id=run_id, created_at=created_at, created_by=user_name, task_id=task_id)
    return result


def get_run(run_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM analysis_runs WHERE id=?", (run_id,))
    if not row:
        return None
    payload = db.loads(row["payload"], {})
    payload.update(run_id=row["id"], created_at=row["created_at"], created_by=row["created_by"], task_id=row["task_id"])
    return payload


def default_window(snapshot: DataSnapshot, days: int = 7) -> tuple[str, str] | None:
    """Kỳ mặc định: `days` ngày kết thúc ở ngày dữ liệu thời tiết mới nhất."""
    latest = snapshot.latest_weather_date()
    if not latest:
        return None
    end = parse_date(latest)
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()
