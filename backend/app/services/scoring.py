"""Scoring ESS / PIS xác định (deterministic). Không dùng LLM để tính điểm.

LƯU Ý: toàn bộ trọng số, đường cong và ngưỡng dưới đây là CẤU HÌNH MINH HỌA cho bản demo,
CHƯA được chuyên gia côn trùng học / dịch tễ học xác nhận. ESS/PIS không phải xác suất mắc bệnh
hay xác suất bùng phát dịch.
"""
from __future__ import annotations

from typing import Any

SCORING_VERSION = "ess-pis-demo-0.1.0"
DEMO_NOTICE = (
    "Trọng số, đường cong và ngưỡng là cấu hình minh họa, chưa được chuyên gia xác nhận. "
    "ESS/PIS chỉ phản ánh mức thuận lợi của điều kiện môi trường theo quy tắc của hệ thống, "
    "không phải xác suất có véc-tơ, xác suất mắc bệnh hay kết luận dịch tễ."
)

# Tỷ lệ trọng số tối thiểu phải có dữ liệu thì mới tính ESS.
MIN_COMPLETENESS = 0.6

SPECIES_REGISTRY: dict[str, dict[str, Any]] = {
    "aedes": {
        "label": "Aedes",
        "configured": True,
        "ess_weights": {"rainfall": 0.25, "temperature": 0.20, "humidity": 0.15, "water": 0.25, "survey": 0.15},
        # Đường cong tuyến tính từng đoạn: [(giá trị, điểm 0-100), ...]
        "curves": {
            # Mưa rất lớn không làm điểm tăng mãi (có thể cuốn trôi ổ chứa nước).
            "rainfall": [(0, 0), (100, 100), (150, 100), (300, 60)],
            "temperature": [(16, 0), (27, 100), (31, 100), (38, 0)],
            "humidity": [(40, 0), (90, 100)],
            "water": [(0, 0), (15, 100)],
        },
        "survey": {"base_when_none_found": 10, "span": 90},
    },
    "anopheles": {"label": "Anopheles", "configured": False},
    "culex": {"label": "Culex", "configured": False},
}

PIS_WEIGHTS = {"ess": 0.35, "water": 0.25, "survey": 0.25, "change": 0.15}
CHANGE_POINTS_PER_ESS = 5  # ChangeScore = clamp(ΔESS × 5, 0, 100); chỉ tính phần ESS tăng

ESS_CLASSES = [
    (0, 25, "very_low", "Rất thấp", "Ít điều kiện thuận lợi"),
    (25, 50, "low", "Thấp", "Có một số điều kiện thuận lợi"),
    (50, 75, "medium", "Trung bình", "Nhiều điều kiện thuận lợi"),
    (75, 90, "high", "Cao", "Điều kiện thuận lợi đáng kể"),
    (90, 100.0001, "very_high", "Rất cao", "Điều kiện thuận lợi nổi bật"),
]
PIS_CLASSES = [
    (0, 25, "none", "Không ưu tiên"),
    (25, 50, "watch", "Theo dõi"),
    (50, 75, "inspect", "Cần kiểm tra"),
    (75, 100.0001, "priority", "Ưu tiên kiểm tra"),
]

COMPONENT_META = {
    "rainfall": {"label": "Lượng mưa tích lũy (quy đổi 7 ngày)", "unit": "mm", "feature": "rainfall_7d"},
    "temperature": {"label": "Nhiệt độ trung bình", "unit": "°C", "feature": "temperature_mean"},
    "humidity": {"label": "Độ ẩm tương đối trung bình", "unit": "%", "feature": "humidity_mean"},
    "water": {"label": "Số điểm nước đọng đang tồn tại", "unit": "điểm", "feature": "water_points_active"},
    "survey": {"label": "Bằng chứng khảo sát thực địa (30 ngày)", "unit": "tỷ lệ dương tính", "feature": "survey_positive_ratio"},
}


def interpolate(curve: list[tuple[float, float]], x: float) -> float:
    """Nội suy tuyến tính từng đoạn, giữ nguyên giá trị biên ngoài khoảng định nghĩa."""
    if x <= curve[0][0]:
        return float(curve[0][1])
    if x >= curve[-1][0]:
        return float(curve[-1][1])
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return float(y1)
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(curve[-1][1])


def classify_ess(value: float | None) -> dict | None:
    if value is None:
        return None
    for lo, hi, key, label, meaning in ESS_CLASSES:
        if lo <= value < hi:
            return {"key": key, "label": label, "meaning": meaning}
    return None


def classify_pis(value: float | None) -> dict | None:
    if value is None:
        return None
    for lo, hi, key, label in PIS_CLASSES:
        if lo <= value < hi:
            return {"key": key, "label": label}
    return None


def _curve_reference(curve: list[tuple[float, float]], unit: str) -> str:
    return " → ".join(f"{x:g}{unit}: {y:g}đ" for x, y in curve)


def _component_explanation(key: str, value: float, score: float) -> str:
    level = "thuận lợi cao" if score >= 75 else "thuận lợi vừa" if score >= 50 else "ít thuận lợi"
    if key == "rainfall":
        extra = " Mưa rất lớn (>150 mm) bị giảm điểm vì có thể cuốn trôi ổ chứa nước." if value > 150 else ""
        return f"Mưa quy đổi 7 ngày {value:g} mm → {level} cho việc hình thành nước đọng.{extra}"
    if key == "temperature":
        return f"Nhiệt độ trung bình {value:g} °C → {level} (khoảng tham chiếu demo 27–31 °C đạt điểm tối đa)."
    if key == "humidity":
        return f"Độ ẩm trung bình {value:g}% → {level} (điểm tăng dần từ 40% đến 90%)."
    if key == "water":
        return f"Có {value:g} điểm nước đọng đang tồn tại → {level} (15 điểm trở lên đạt điểm tối đa)."
    if key == "survey":
        return (
            f"{value * 100:.0f}% lượt khảo sát hợp lệ trong 30 ngày có ghi nhận ấu trùng/muỗi trưởng thành → {level}. "
            "Lượt “chưa khảo sát” không được tính là bằng chứng không có véc-tơ."
        )
    return ""


def compute_ess(features: dict[str, Any], species: str = "aedes") -> dict[str, Any]:
    """Tính ESS từ bộ đặc trưng. Giá trị None nghĩa là THIẾU dữ liệu (không coi là 0)."""
    spec = SPECIES_REGISTRY.get(species)
    if not spec or not spec.get("configured"):
        return {
            "status": "unsupported_species",
            "ess": None,
            "ess_class": None,
            "completeness": 0.0,
            "components": [],
            "missing": [],
            "message": f"Loài “{species}” chưa có bộ tham số trong bản MVP (chỉ cấu hình Aedes).",
            "version": SCORING_VERSION,
        }

    weights = spec["ess_weights"]
    components: list[dict] = []
    missing: list[dict] = []
    for key, weight in weights.items():
        meta = COMPONENT_META[key]
        value = features.get(meta["feature"])
        info = features.get("_meta", {}).get(meta["feature"], {})
        comp = {
            "key": key,
            "label": meta["label"],
            "unit": meta["unit"],
            "value": value,
            "weight": weight,
            "source": info.get("source"),
            "detail": info.get("detail"),
        }
        if value is None:
            comp.update(score=None, effective_weight=0.0, contribution=None, missing=True,
                        explanation=info.get("missing_reason") or "Thiếu dữ liệu — không tính thành phần này (không coi là 0).",
                        reference=None)
            missing.append({"key": key, "label": meta["label"],
                            "reason": info.get("missing_reason") or "Không có dữ liệu trong khoảng thời gian đã chọn."})
        else:
            if key == "survey":
                score = spec["survey"]["base_when_none_found"] + spec["survey"]["span"] * float(value)
                reference = "Điểm = 10 + 90 × tỷ lệ lượt khảo sát dương tính"
            else:
                score = interpolate(spec["curves"][key], float(value))
                reference = _curve_reference(spec["curves"][key], "")
            comp.update(score=round(score, 1), missing=False, reference=reference,
                        explanation=_component_explanation(key, float(value), score))
        components.append(comp)

    available_weight = sum(c["weight"] for c in components if not c["missing"])
    completeness = round(available_weight, 4)
    if available_weight < MIN_COMPLETENESS:
        return {
            "status": "insufficient_data",
            "ess": None,
            "ess_class": None,
            "completeness": completeness,
            "components": components,
            "missing": missing,
            "message": (
                f"Chỉ có {completeness * 100:.0f}% trọng số có dữ liệu (yêu cầu tối thiểu {MIN_COMPLETENESS * 100:.0f}%). "
                "Hệ thống không tính ESS để tránh kết luận từ dữ liệu không đủ."
            ),
            "version": SCORING_VERSION,
        }

    ess = 0.0
    for comp in components:
        if comp["missing"]:
            continue
        comp["effective_weight"] = round(comp["weight"] / available_weight, 4)
        comp["contribution"] = round(comp["score"] * comp["weight"] / available_weight, 2)
        ess += comp["score"] * comp["weight"] / available_weight
    ess = round(ess, 1)
    return {
        "status": "ok" if not missing else "partial",
        "ess": ess,
        "ess_class": classify_ess(ess),
        "completeness": completeness,
        "components": components,
        "missing": missing,
        "message": None if not missing else "Thiếu một phần dữ liệu: trọng số được chia lại trên các thành phần hợp lệ.",
        "version": SCORING_VERSION,
    }


def compute_change_score(ess_now: float | None, ess_prev: float | None) -> float | None:
    if ess_now is None or ess_prev is None:
        return None
    return round(max(0.0, min(100.0, (ess_now - ess_prev) * CHANGE_POINTS_PER_ESS)), 1)


def compute_pis(ess: float | None, water_score: float | None, survey_score: float | None,
                change_score: float | None) -> dict[str, Any]:
    """PIS = 0.35×ESS + 0.25×WaterScore + 0.25×SurveyEvidence + 0.15×ChangeScore (trọng số minh họa)."""
    if ess is None:
        return {"pis": None, "pis_class": None, "components": [], "missing": ["ess"],
                "message": "Không tính PIS vì chưa có ESS."}
    parts = {"ess": ess, "water": water_score, "survey": survey_score, "change": change_score}
    labels = {"ess": "ESS", "water": "WaterScore (điểm nước đọng)", "survey": "SurveyEvidence (khảo sát)",
              "change": "ChangeScore (mức tăng ESS so với kỳ trước)"}
    available = sum(PIS_WEIGHTS[k] for k, v in parts.items() if v is not None)
    comps, missing, total = [], [], 0.0
    for key, value in parts.items():
        if value is None:
            missing.append(key)
            comps.append({"key": key, "label": labels[key], "score": None, "weight": PIS_WEIGHTS[key],
                          "effective_weight": 0.0, "contribution": None, "missing": True})
            continue
        contribution = value * PIS_WEIGHTS[key] / available
        total += contribution
        comps.append({"key": key, "label": labels[key], "score": round(value, 1), "weight": PIS_WEIGHTS[key],
                      "effective_weight": round(PIS_WEIGHTS[key] / available, 4),
                      "contribution": round(contribution, 2), "missing": False})
    pis = round(total, 1)
    return {"pis": pis, "pis_class": classify_pis(pis), "components": comps, "missing": missing,
            "message": None if not missing else "Thiếu một phần thành phần PIS: trọng số được chia lại."}


def collect_sources(components: list[dict]) -> list[str]:
    """Gộp danh sách nguồn dữ liệu (không trùng) từ các thành phần điểm."""
    found: set[str] = set()
    for comp in components:
        for part in (comp.get("source") or "").split(";"):
            if part.strip():
                found.add(part.strip())
    return sorted(found)


def public_config() -> dict[str, Any]:
    """Cấu hình scoring để hiển thị (chỉ đọc) trên giao diện và lưu kèm kết quả."""
    return {
        "version": SCORING_VERSION,
        "notice": DEMO_NOTICE,
        "min_completeness": MIN_COMPLETENESS,
        "species": SPECIES_REGISTRY,
        "pis_weights": PIS_WEIGHTS,
        "change_points_per_ess": CHANGE_POINTS_PER_ESS,
        "ess_classes": [{"min": lo, "max": min(hi, 100), "key": k, "label": lbl, "meaning": m}
                        for lo, hi, k, lbl, m in ESS_CLASSES],
        "pis_classes": [{"min": lo, "max": min(hi, 100), "key": k, "label": lbl} for lo, hi, k, lbl in PIS_CLASSES],
    }
