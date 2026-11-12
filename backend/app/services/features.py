"""Tạo đặc trưng (feature engineering) từ dữ liệu đã lưu. Thiếu dữ liệu → None, không thay bằng 0."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import ceil

from .. import db

ALL_SOURCES = ("weather", "water", "survey")
SURVEY_LOOKBACK_DAYS = 30
MIN_DAY_COVERAGE = 0.5  # cần ít nhất 50% số ngày trong kỳ có giá trị thì mới tổng hợp

SURVEY_RESULT_LABELS = {
    "larvae_present": "Có ấu trùng/bọ gậy",
    "adult_present": "Có muỗi trưởng thành",
    "none_found": "Đã khảo sát, không ghi nhận",
    "not_surveyed": "Chưa khảo sát",
}
POSITIVE_RESULTS = {"larvae_present", "adult_present"}


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


class DataSnapshot:
    """Nạp dữ liệu một lần vào bộ nhớ để tính nhiều khu vực / nhiều ngày mà không truy vấn lặp."""

    def __init__(self) -> None:
        self.weather: dict[int, dict[str, dict]] = defaultdict(dict)
        for row in db.query("SELECT * FROM weather"):
            self.weather[row["area_id"]][row["obs_date"]] = row
        self.water: dict[int, list[dict]] = defaultdict(list)
        for row in db.query("SELECT * FROM water_points"):
            self.water[row["area_id"]].append(row)
        self.surveys: dict[int, list[dict]] = defaultdict(list)
        for row in db.query("SELECT * FROM surveys"):
            self.surveys[row["area_id"]].append(row)

    def latest_weather_date(self) -> str | None:
        dates = [d for per_area in self.weather.values() for d in per_area]
        return max(dates) if dates else None

    def earliest_weather_date(self) -> str | None:
        dates = [d for per_area in self.weather.values() for d in per_area]
        return min(dates) if dates else None

    # ------------------------------------------------------------------
    def features(self, area_id: int, start: str, end: str, species: str = "aedes",
                 sources: tuple[str, ...] = ALL_SOURCES) -> dict:
        d0, d1 = parse_date(start), parse_date(end)
        n_days = (d1 - d0).days + 1
        days = [(d0 + timedelta(days=i)).isoformat() for i in range(n_days)]
        min_days = max(1, ceil(n_days * MIN_DAY_COVERAGE))
        feats: dict = {"_meta": {}, "window_days": n_days, "start": start, "end": end}

        def not_selected(feature: str, label: str) -> None:
            feats[feature] = None
            feats["_meta"][feature] = {"missing_reason": f"Nguồn “{label}” không được chọn cho lần phân tích này."}

        # --- Thời tiết ---------------------------------------------------
        if "weather" not in sources:
            for f in ("rainfall_7d", "temperature_mean", "humidity_mean"):
                not_selected(f, "dữ liệu thời tiết")
            feats["weather_rows"] = []
        else:
            rows = [self.weather[area_id].get(d) for d in days]
            present = [r for r in rows if r]
            feats["weather_rows"] = [
                {"date": d, **({k: r[k] for k in ("rainfall_mm", "temperature_c", "humidity_pct", "source")} if r else
                               {"rainfall_mm": None, "temperature_c": None, "humidity_pct": None, "source": None})}
                for d, r in zip(days, rows)
            ]
            srcs = sorted({r["source"] for r in present}) or None
            src_text = "; ".join(srcs) if srcs else None

            def series(col: str) -> list[float]:
                return [r[col] for r in present if r[col] is not None]

            rain = series("rainfall_mm")
            if len(rain) >= min_days:
                total = sum(rain)
                feats["rainfall_total"] = round(total, 1)
                feats["rainfall_7d"] = round(total / len(rain) * 7, 1)
                feats["_meta"]["rainfall_7d"] = {
                    "source": src_text,
                    "detail": f"Tổng {total:.1f} mm trên {len(rain)}/{n_days} ngày có số liệu; quy đổi về 7 ngày.",
                }
            else:
                feats["rainfall_7d"] = None
                feats["_meta"]["rainfall_7d"] = {
                    "missing_reason": f"Chỉ có {len(rain)}/{n_days} ngày có số liệu mưa (cần ≥ {min_days})."}

            for col, feat, unit in (("temperature_c", "temperature_mean", "°C"), ("humidity_pct", "humidity_mean", "%")):
                vals = series(col)
                name = "nhiệt độ" if col == "temperature_c" else "độ ẩm"
                if len(vals) >= min_days:
                    feats[feat] = round(sum(vals) / len(vals), 1)
                    feats["_meta"][feat] = {
                        "source": src_text,
                        "detail": f"Trung bình {len(vals)}/{n_days} ngày; min {min(vals):g}{unit}, max {max(vals):g}{unit}.",
                    }
                else:
                    feats[feat] = None
                    feats["_meta"][feat] = {
                        "missing_reason": f"Chỉ có {len(vals)}/{n_days} ngày có số liệu {name} (cần ≥ {min_days})."}

        # --- Điểm nước đọng ----------------------------------------------
        if "water" not in sources:
            not_selected("water_points_active", "điểm nước đọng")
            feats["water_rows"] = []
        else:
            pts = [p for p in self.water[area_id] if p["observed_date"] <= end]
            active = [p for p in pts if p["status"] == "active"]
            feats["water_rows"] = pts
            # Chưa có bản ghi nào ≠ xác nhận không có nước đọng → coi là thiếu dữ liệu.
            if not pts:
                feats["water_points_active"] = None
                feats["_meta"]["water_points_active"] = {
                    "missing_reason": "Chưa có bản ghi điểm nước đọng nào cho khu vực (chưa ghi nhận ≠ không có)."}
            else:
                feats["water_points_active"] = len(active)
                feats["_meta"]["water_points_active"] = {
                    "source": "; ".join(sorted({p["source"] for p in pts})),
                    "detail": f"{len(active)} điểm đang tồn tại / {len(pts)} điểm đã ghi nhận đến {end}.",
                }

        # --- Khảo sát thực địa -------------------------------------------
        if "survey" not in sources:
            not_selected("survey_positive_ratio", "khảo sát thực địa")
            feats["survey_rows"] = []
        else:
            lookback = (d1 - timedelta(days=SURVEY_LOOKBACK_DAYS - 1)).isoformat()
            rows = [s for s in self.surveys[area_id]
                    if lookback <= s["survey_date"] <= end and s["species"] == species]
            valid = [s for s in rows if s["result"] != "not_surveyed"]
            positive = [s for s in valid if s["result"] in POSITIVE_RESULTS]
            feats["survey_rows"] = rows
            feats["survey_valid_count"] = len(valid)
            feats["survey_not_surveyed_count"] = len(rows) - len(valid)
            if not valid:
                reason = "Không có lượt khảo sát hợp lệ trong 30 ngày."
                if rows:
                    reason = (f"Có {len(rows)} bản ghi nhưng đều ở trạng thái “chưa khảo sát” — "
                              "không dùng làm bằng chứng không có véc-tơ.")
                feats["survey_positive_ratio"] = None
                feats["_meta"]["survey_positive_ratio"] = {"missing_reason": reason}
            else:
                feats["survey_positive_ratio"] = round(len(positive) / len(valid), 3)
                feats["_meta"]["survey_positive_ratio"] = {
                    "source": "; ".join(sorted({s["source"] for s in valid})),
                    "detail": f"{len(positive)}/{len(valid)} lượt khảo sát hợp lệ có ghi nhận"
                              + (f"; bỏ qua {len(rows) - len(valid)} bản ghi “chưa khảo sát”." if len(rows) > len(valid) else "."),
                }
        return feats
