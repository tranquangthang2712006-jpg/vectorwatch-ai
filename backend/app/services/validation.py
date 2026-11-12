"""Kiểm tra dữ liệu nhập (form / CSV / Excel) theo từng dòng, từng trường, kèm gợi ý sửa.

Nguyên tắc: không tự sửa dữ liệu nguồn, không tự ghi đè bản ghi cũ; dòng lỗi bị từ chối và báo rõ lý do.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime

from .. import db
from . import geo

KINDS = {
    "weather": {
        "label": "Dữ liệu thời tiết",
        "columns": ["area_code", "date", "rainfall_mm", "temperature_c", "humidity_pct", "source"],
        "example": ["KV-A", "2026-01-15", "12.5", "28.4", "81", "Trạm quan trắc mẫu"],
    },
    "water": {
        "label": "Điểm nước đọng",
        "columns": ["code", "latitude", "longitude", "water_type", "status", "persistence_days", "observed_date", "notes", "source"],
        "example": ["", "21.0251", "105.7852", "Lốp xe cũ", "active", "5", "2026-01-15", "Sau nhà văn hóa", "Khảo sát thực địa"],
    },
    "survey": {
        "label": "Khảo sát thực địa",
        "columns": ["code", "latitude", "longitude", "survey_date", "species", "result", "vector_count", "notes", "source"],
        "example": ["", "21.0251", "105.7852", "2026-01-15", "aedes", "larvae_present", "12", "Bọ gậy trong chum nước", "Khảo sát thực địa"],
    },
}

WATER_STATUS = {"active": "active", "đang tồn tại": "active", "con nuoc": "active", "resolved": "resolved",
                "đã xử lý": "resolved", "da xu ly": "resolved"}
SURVEY_RESULTS = {
    "larvae_present": "larvae_present", "có ấu trùng": "larvae_present", "có bọ gậy": "larvae_present",
    "adult_present": "adult_present", "có muỗi trưởng thành": "adult_present",
    "none_found": "none_found", "không ghi nhận": "none_found",
    "not_surveyed": "not_surveyed", "chưa khảo sát": "not_surveyed",
}
SPECIES = {"aedes", "anopheles", "culex"}
RANGES = {"rainfall_mm": (0, 500), "temperature_c": (-5, 50), "humidity_pct": (0, 100)}


def _err(field: str, message: str, fix: str) -> dict:
    return {"field": field, "message": message, "fix": fix}


def _text(row: dict, key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def _parse_date(value: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _check_date(row: dict, key: str, errors: list, data: dict) -> None:
    raw = _text(row, key)
    if not raw:
        errors.append(_err(key, "Thiếu ngày.", "Nhập ngày theo dạng YYYY-MM-DD (ví dụ 2026-01-15)."))
        return
    parsed = _parse_date(raw)
    if not parsed:
        errors.append(_err(key, f"Ngày “{raw}” không đúng định dạng.", "Dùng dạng YYYY-MM-DD hoặc DD/MM/YYYY."))
    elif parsed > date.today():
        errors.append(_err(key, f"Ngày {parsed.isoformat()} nằm ở tương lai.", "Chỉ nhập số liệu đã quan sát; kiểm tra lại năm/tháng."))
    else:
        data[key] = parsed.isoformat()


def _check_coords(row: dict, errors: list, data: dict, areas: list[dict]) -> None:
    lat_raw, lng_raw = _text(row, "latitude"), _text(row, "longitude")
    lat = _parse_float(lat_raw) if lat_raw else None
    lng = _parse_float(lng_raw) if lng_raw else None
    if lat is None:
        errors.append(_err("latitude", "Thiếu hoặc sai vĩ độ.", "Nhập vĩ độ dạng số thập phân WGS84, ví dụ 21.0251."))
    if lng is None:
        errors.append(_err("longitude", "Thiếu hoặc sai kinh độ.", "Nhập kinh độ dạng số thập phân WGS84, ví dụ 105.7852."))
    if lat is None or lng is None:
        return
    if not (-90 <= lat <= 90) and -90 <= lng <= 90 and geo.find_area(lng, lat, areas):
        errors.append(_err("latitude", f"Vĩ độ {lat:g} không hợp lệ — có vẻ vĩ độ và kinh độ bị đảo chỗ.",
                           f"Đổi chỗ hai giá trị: latitude={lng:g}, longitude={lat:g}."))
        return
    if not (-90 <= lat <= 90):
        errors.append(_err("latitude", f"Vĩ độ {lat:g} nằm ngoài khoảng −90…90.", "Kiểm tra dấu thập phân hoặc thứ tự cột vĩ độ/kinh độ."))
        return
    if not (-180 <= lng <= 180):
        errors.append(_err("longitude", f"Kinh độ {lng:g} nằm ngoài khoảng −180…180.", "Kiểm tra dấu thập phân hoặc thứ tự cột."))
        return
    area = geo.find_area(lat, lng, areas)
    if not area:
        swapped = geo.find_area(lng, lat, areas)
        if swapped:
            errors.append(_err("latitude", "Tọa độ nằm ngoài khu vực thí điểm — có vẻ vĩ độ và kinh độ bị đảo chỗ.",
                               f"Đổi chỗ hai giá trị: latitude={lng:g}, longitude={lat:g}."))
        else:
            ext = geo.pilot_extent(areas)
            hint = (f"Khu vực thí điểm nằm trong vĩ độ {ext['min_lat']:.4f}–{ext['max_lat']:.4f}, "
                    f"kinh độ {ext['min_lng']:.4f}–{ext['max_lng']:.4f}." if ext else "")
            errors.append(_err("latitude", f"Tọa độ ({lat:g}, {lng:g}) nằm ngoài mọi khu vực giám sát; không gắn lên bản đồ.",
                               "Kiểm tra lại tọa độ GPS. " + hint))
        return
    data.update(latitude=round(lat, 6), longitude=round(lng, 6), area_id=area["id"], area_code=area["code"])


def validate_rows(kind: str, raw_rows: list[dict]) -> dict:
    """Trả về kết quả kiểm tra cho từng dòng. Không ghi CSDL."""
    if kind not in KINDS:
        raise ValueError(f"Loại dữ liệu không hỗ trợ: {kind}")
    areas = geo.load_areas()
    area_by_code = {a["code"].upper(): a for a in areas}
    existing_weather = {(r["area_id"], r["obs_date"]) for r in db.query("SELECT area_id, obs_date FROM weather")} if kind == "weather" else set()
    table = {"water": "water_points", "survey": "surveys"}.get(kind)
    existing_codes = {r["code"] for r in db.query(f"SELECT code FROM {table}")} if table else set()

    seen: set = set()
    results = []
    for index, row in enumerate(raw_rows, start=1):
        errors: list[dict] = []
        warnings: list[dict] = []
        data: dict = {}
        duplicate = None

        if kind == "weather":
            code = _text(row, "area_code").upper()
            if not code:
                errors.append(_err("area_code", "Thiếu mã khu vực.", "Nhập mã khu vực, ví dụ KV-A (xem danh sách ở bộ lọc khu vực)."))
            elif code not in area_by_code:
                errors.append(_err("area_code", f"Không có khu vực “{code}”.", "Dùng một trong các mã: " + ", ".join(sorted(area_by_code)) + "."))
            else:
                data["area_code"] = code
                data["area_id"] = area_by_code[code]["id"]
            _check_date(row, "date", errors, data)
            measured = 0
            for field, (lo, hi) in RANGES.items():
                raw = _text(row, field)
                if not raw:
                    data[field] = None
                    warnings.append(_err(field, "Để trống — sẽ được lưu là THIẾU (không phải 0).", "Bổ sung nếu có số liệu."))
                    continue
                value = _parse_float(raw)
                if value is None:
                    errors.append(_err(field, f"“{raw}” không phải là số.", "Chỉ nhập số, dùng dấu chấm cho phần thập phân."))
                elif not (lo <= value <= hi):
                    errors.append(_err(field, f"Giá trị {value:g} ngoài khoảng hợp lý {lo}…{hi}.", "Kiểm tra đơn vị (mm, °C, %) và lỗi gõ nhầm."))
                else:
                    data[field] = value
                    measured += 1
            if measured == 0 and not any(e["field"] in RANGES for e in errors):
                errors.append(_err("rainfall_mm", "Dòng không có số liệu đo nào.", "Nhập ít nhất một trong: lượng mưa, nhiệt độ, độ ẩm."))
            data["source"] = _text(row, "source") or "Nhập thủ công"
            key = (data.get("area_id"), data.get("date"))
            if None not in key:
                if key in seen:
                    duplicate = "file"
                elif key in existing_weather:
                    duplicate = "db"
                seen.add(key)
        else:
            code = _text(row, "code").upper()
            data["code"] = code or None
            _check_coords(row, errors, data, areas)
            date_field = "observed_date" if kind == "water" else "survey_date"
            _check_date(row, date_field, errors, data)
            if kind == "water":
                water_type = _text(row, "water_type")
                if not water_type:
                    errors.append(_err("water_type", "Thiếu loại điểm nước đọng.", "Ví dụ: Lốp xe cũ, Chum/vại, Vũng nước, Cống rãnh."))
                data["water_type"] = water_type
                status_raw = _text(row, "status").lower() or "active"
                if status_raw not in WATER_STATUS:
                    errors.append(_err("status", f"Trạng thái “{status_raw}” không hợp lệ.", "Dùng active (đang tồn tại) hoặc resolved (đã xử lý)."))
                else:
                    data["status"] = WATER_STATUS[status_raw]
                raw = _text(row, "persistence_days")
                if raw:
                    value = _parse_float(raw)
                    if value is None or value < 0:
                        errors.append(_err("persistence_days", f"“{raw}” không hợp lệ.", "Nhập số ngày ≥ 0 hoặc để trống."))
                    else:
                        data["persistence_days"] = int(value)
                else:
                    data["persistence_days"] = None
            else:
                species = _text(row, "species").lower() or "aedes"
                if species not in SPECIES:
                    errors.append(_err("species", f"Loài “{species}” không có trong danh mục.", "Dùng aedes, anopheles hoặc culex."))
                data["species"] = species
                result_raw = _text(row, "result").lower()
                if result_raw not in SURVEY_RESULTS:
                    errors.append(_err("result", "Thiếu hoặc sai kết quả khảo sát.",
                                       "Dùng: larvae_present, adult_present, none_found hoặc not_surveyed."))
                else:
                    data["result"] = SURVEY_RESULTS[result_raw]
                    if data["result"] == "not_surveyed":
                        warnings.append(_err("result", "“Chưa khảo sát” sẽ không được dùng làm bằng chứng không có véc-tơ.", "Cập nhật khi có kết quả thực địa."))
                raw = _text(row, "vector_count")
                if raw:
                    value = _parse_float(raw)
                    if value is None or value < 0 or value != int(value):
                        errors.append(_err("vector_count", f"“{raw}” không hợp lệ.", "Nhập số nguyên ≥ 0 hoặc để trống (trống = không đếm)."))
                    else:
                        data["vector_count"] = int(value)
                else:
                    data["vector_count"] = None
            data["notes"] = _text(row, "notes") or None
            data["source"] = _text(row, "source") or "Nhập thủ công"
            if code:
                if code in seen:
                    duplicate = "file"
                elif code in existing_codes:
                    duplicate = "db"
                seen.add(code)

        if duplicate == "file":
            errors.append(_err("date" if kind == "weather" else "code", "Trùng với một dòng phía trên trong cùng tệp.",
                               "Xóa dòng trùng hoặc gộp số liệu trước khi nhập."))
        results.append({"row": index, "raw": {k: ("" if v is None else str(v)) for k, v in row.items()},
                        "data": data, "errors": errors, "warnings": warnings,
                        "duplicate": duplicate == "db", "valid": not errors})

    valid = sum(1 for r in results if r["valid"])
    return {
        "kind": kind,
        "columns": KINDS[kind]["columns"],
        "rows": results,
        "summary": {"total": len(results), "valid": valid, "invalid": len(results) - valid,
                    "duplicates": sum(1 for r in results if r["valid"] and r["duplicate"])},
    }


def _next_code(prefix: str, table: str) -> str:
    rows = db.query(f"SELECT code FROM {table} WHERE code LIKE ?", (prefix + "-%",))
    numbers = [int(r["code"].split("-")[-1]) for r in rows if r["code"].split("-")[-1].isdigit()]
    return f"{prefix}-{(max(numbers) + 1 if numbers else 1):04d}"


def commit_rows(kind: str, raw_rows: list[dict], user_name: str, filename: str | None,
                duplicate_policy: str = "skip") -> dict:
    """Kiểm tra lại phía máy chủ rồi lưu các dòng hợp lệ. Bản ghi trùng chỉ bị ghi đè khi policy='overwrite'."""
    if duplicate_policy not in ("skip", "overwrite"):
        raise ValueError("duplicate_policy phải là 'skip' hoặc 'overwrite'.")
    report = validate_rows(kind, raw_rows)
    batch_id = f"BATCH-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    added = updated = skipped = 0
    rejected = report["summary"]["invalid"]
    for item in report["rows"]:
        if not item["valid"]:
            continue
        d = item["data"]
        if item["duplicate"] and duplicate_policy == "skip":
            skipped += 1
            continue
        if kind == "weather":
            if item["duplicate"]:
                db.execute("""UPDATE weather SET rainfall_mm=?, temperature_c=?, humidity_pct=?, source=?, batch_id=?
                              WHERE area_id=? AND obs_date=?""",
                           (d["rainfall_mm"], d["temperature_c"], d["humidity_pct"], d["source"], batch_id, d["area_id"], d["date"]))
                updated += 1
            else:
                db.execute("""INSERT INTO weather (area_id, obs_date, rainfall_mm, temperature_c, humidity_pct, source, batch_id)
                              VALUES (?,?,?,?,?,?,?)""",
                           (d["area_id"], d["date"], d["rainfall_mm"], d["temperature_c"], d["humidity_pct"], d["source"], batch_id))
                added += 1
        elif kind == "water":
            if item["duplicate"]:
                db.execute("""UPDATE water_points SET area_id=?, latitude=?, longitude=?, water_type=?, status=?,
                              persistence_days=?, observed_date=?, notes=?, source=?, batch_id=? WHERE code=?""",
                           (d["area_id"], d["latitude"], d["longitude"], d["water_type"], d["status"], d["persistence_days"],
                            d["observed_date"], d["notes"], d["source"], batch_id, d["code"]))
                updated += 1
            else:
                code = d["code"] or _next_code("WP", "water_points")
                db.execute("""INSERT INTO water_points (code, area_id, latitude, longitude, water_type, status,
                              persistence_days, observed_date, notes, source, batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (code, d["area_id"], d["latitude"], d["longitude"], d["water_type"], d["status"],
                            d["persistence_days"], d["observed_date"], d["notes"], d["source"], batch_id))
                added += 1
        else:
            if item["duplicate"]:
                db.execute("""UPDATE surveys SET area_id=?, latitude=?, longitude=?, survey_date=?, species=?, result=?,
                              vector_count=?, notes=?, entered_by=?, source=?, batch_id=? WHERE code=?""",
                           (d["area_id"], d["latitude"], d["longitude"], d["survey_date"], d["species"], d["result"],
                            d["vector_count"], d["notes"], user_name, d["source"], batch_id, d["code"]))
                updated += 1
            else:
                code = d["code"] or _next_code("SV", "surveys")
                db.execute("""INSERT INTO surveys (code, area_id, latitude, longitude, survey_date, species, result,
                              vector_count, notes, entered_by, source, batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (code, d["area_id"], d["latitude"], d["longitude"], d["survey_date"], d["species"], d["result"],
                            d["vector_count"], d["notes"], user_name, d["source"], batch_id))
                added += 1
    db.execute("""INSERT INTO import_batches (id, kind, filename, user_name, created_at, rows_added, rows_updated,
                  rows_rejected, rows_skipped) VALUES (?,?,?,?,?,?,?,?,?)""",
               (batch_id, kind, filename, user_name, db.now_iso(), added, updated, rejected, skipped))
    return {"batch_id": batch_id, "added": added, "updated": updated, "rejected": rejected, "skipped": skipped,
            "duplicate_policy": duplicate_policy, "report": report}


def parse_upload(filename: str, content: bytes, kind: str) -> list[dict]:
    """Đọc CSV hoặc Excel (.xlsx) thành danh sách dòng theo tên cột."""
    name = (filename or "").lower()
    columns = KINDS[kind]["columns"]
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
        records = []
        for values in rows[1:]:
            if values is None or all(v is None or str(v).strip() == "" for v in values):
                continue
            record = {}
            for key, value in zip(header, values):
                if isinstance(value, (datetime, date)):
                    value = value.strftime("%Y-%m-%d")
                record[key] = value
            records.append(record)
    elif name.endswith(".csv") or name.endswith(".txt"):
        text = content.decode("utf-8-sig", errors="replace")
        delimiter = ";" if text.splitlines() and text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        records = [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader
                   if any((v or "").strip() for v in row.values())]
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
    else:
        raise ValueError("Chỉ hỗ trợ tệp .csv hoặc .xlsx. Hãy tải tệp mẫu và lưu đúng định dạng.")
    required = [c for c in columns if c not in ("code", "notes", "source", "status", "persistence_days", "vector_count",
                                                "rainfall_mm", "temperature_c", "humidity_pct", "species")]
    missing = [c for c in required if c not in header]
    if missing:
        raise ValueError("Tệp thiếu cột bắt buộc: " + ", ".join(missing) + ". Hãy dùng tệp mẫu để có đúng tên cột.")
    if len(records) > 2000:
        raise ValueError("Tệp có hơn 2000 dòng. Hãy chia nhỏ tệp để xem trước và kiểm tra dễ hơn.")
    return records


def template_csv(kind: str) -> str:
    spec = KINDS[kind]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(spec["columns"])
    writer.writerow(spec["example"])
    return out.getvalue()
