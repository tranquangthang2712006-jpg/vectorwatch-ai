"""Sinh dữ liệu mẫu GIẢ LẬP, nhất quán và lặp lại được (seed cố định).

Toàn bộ khu vực, tọa độ, thời tiết, điểm nước đọng và khảo sát dưới đây là dữ liệu tổng hợp để trình diễn;
KHÔNG phải số liệu quan trắc thật và các ô khu vực KHÔNG trùng ranh giới hành chính thật.

Chạy lại từ đầu:  python -m app.seed --reset
"""
from __future__ import annotations

import random
import secrets
import sys
from datetime import date, timedelta

from . import config, db
from .security import hash_password
from .services.geo import point_in_polygon

SOURCE = config.SAMPLE_SOURCE_LABEL
ORIGIN_LAT, ORIGIN_LNG = 21.0200, 105.7800
CELL_LAT, CELL_LNG = 0.0125, 0.0150
COLS, ROWS = 4, 3
DAYS = 35

# code: (mưa 7 ngày gần nhất mm, mưa tuần trước mm, nhiệt độ TB °C, độ ẩm TB %, số điểm nước đọng đang tồn tại,
#        kết quả khảo sát gần đây)
PROFILES = {
    "A": (85, 30, 29.0, 82, 18, ["larvae_present", "larvae_present", "adult_present", "larvae_present", "none_found"]),
    "B": (25, 28, 26.0, 65, 3, ["none_found", "none_found", "none_found"]),
    "C": (65, 40, 28.0, 78, 12, ["larvae_present", "none_found", "adult_present", "none_found"]),
    "D": (70, 55, 28.5, None, 9, ["larvae_present", "none_found", "none_found"]),   # thiếu độ ẩm kỳ gần nhất
    "E": (55, 50, 27.5, 76, 7, ["not_surveyed", "not_surveyed"]),                    # chỉ có bản ghi "chưa khảo sát"
    "F": (40, 45, 27.0, 72, 5, ["none_found", "larvae_present", "none_found"]),
    "G": (95, 35, 29.5, 85, 14, ["larvae_present", "larvae_present", "none_found", "adult_present"]),
    "H": (15, 20, 25.0, 60, 2, ["none_found", "none_found"]),
    "I": (60, 60, 28.0, 80, 10, ["larvae_present", "none_found"]),
    "J": (30, 25, 26.5, 68, 4, []),                                                   # chưa có khảo sát nào
    "K": (180, 70, 27.5, 88, 11, ["larvae_present", "adult_present", "none_found"]), # mưa rất lớn
    "L": (45, 40, 30.5, 70, 6, ["none_found", "none_found", "larvae_present", "none_found"]),
}
WATER_TYPES = ["Lốp xe cũ", "Chum/vại chứa nước", "Phế thải chứa nước", "Vũng nước", "Cống rãnh", "Chậu cây cảnh", "Thùng phuy"]
USERS = [
    ("admin@vectorwatch.local", "Quản trị viên (demo)", "admin"),
    ("analyst@vectorwatch.local", "Chuyên viên phân tích (demo)", "analyst"),
    ("officer@vectorwatch.local", "Cán bộ giám sát (demo)", "officer"),
    ("viewer@vectorwatch.local", "Giám khảo / Người xem (demo)", "viewer"),
]


def _grid_vertices(rng: random.Random) -> list[list[tuple[float, float]]]:
    """Lưới đỉnh có nhiễu nhẹ để các ô chung cạnh nhưng không vuông vức."""
    vertices = []
    for r in range(ROWS + 1):
        row = []
        for c in range(COLS + 1):
            jitter_lat = rng.uniform(-0.0022, 0.0022) if 0 < r < ROWS else rng.uniform(-0.0008, 0.0008)
            jitter_lng = rng.uniform(-0.0028, 0.0028) if 0 < c < COLS else rng.uniform(-0.0008, 0.0008)
            row.append((round(ORIGIN_LAT + r * CELL_LAT + jitter_lat, 6), round(ORIGIN_LNG + c * CELL_LNG + jitter_lng, 6)))
        vertices.append(row)
    return vertices


def _spread(total: float, n: int, rng: random.Random) -> list[float]:
    weights = [rng.random() ** 2 if rng.random() > 0.35 else 0.0 for _ in range(n)]
    if sum(weights) == 0:
        weights[rng.randrange(n)] = 1.0
    scale = total / sum(weights)
    values = [round(w * scale, 1) for w in weights]
    values[values.index(max(values))] = round(values[values.index(max(values))] + (total - sum(values)), 1)
    return values


def _around(mean: float, n: int, spread: float, rng: random.Random) -> list[float]:
    noise = [rng.uniform(-spread, spread) for _ in range(n)]
    shift = sum(noise) / n
    return [round(mean + x - shift, 1) for x in noise]


def _random_point(polygon: list[list[float]], rng: random.Random) -> tuple[float, float]:
    lats = [p[0] for p in polygon]
    lngs = [p[1] for p in polygon]
    for _ in range(500):
        lat = rng.uniform(min(lats), max(lats))
        lng = rng.uniform(min(lngs), max(lngs))
        # lùi vào trong một chút để điểm không nằm sát ranh giới
        c_lat, c_lng = sum(lats) / len(lats), sum(lngs) / len(lngs)
        lat, lng = c_lat + (lat - c_lat) * 0.85, c_lng + (lng - c_lng) * 0.85
        if point_in_polygon(lat, lng, polygon):
            return round(lat, 6), round(lng, 6)
    return round(sum(lats) / len(lats), 6), round(sum(lngs) / len(lngs), 6)


def seed(reset: bool = False) -> bool:
    """Tạo CSDL và dữ liệu mẫu nếu chưa có. Trả về True nếu vừa seed."""
    if reset and config.DB_PATH.exists():
        for suffix in ("", "-wal", "-shm"):
            path = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
            if path.exists():
                path.unlink()
    db.init_schema()
    if db.query_one("SELECT id FROM areas LIMIT 1"):
        return False

    rng = random.Random(20260101)
    today = date.today()
    now = db.now_iso()

    # --- Tài khoản demo -------------------------------------------------
    password = config.DEMO_PASSWORD
    generated = False
    if not password:
        password = secrets.token_urlsafe(9)
        generated = True
    for email, name, role in USERS:
        db.execute("INSERT INTO users (email, full_name, role, password_hash, created_at) VALUES (?,?,?,?,?)",
                   (email, name, role, hash_password(password), now))
    if generated:
        print("=" * 72)
        print("Chưa cấu hình VW_DEMO_PASSWORD → đã sinh mật khẩu ngẫu nhiên cho 4 tài khoản demo:")
        print(f"    {password}")
        print("Hãy lưu lại (chỉ in một lần) hoặc đặt VW_DEMO_PASSWORD trong .env rồi chạy `python -m app.seed --reset`.")
        print("=" * 72)

    # --- Khu vực (ô lưới giả lập) --------------------------------------
    vertices = _grid_vertices(rng)
    codes = list(PROFILES)
    areas = {}
    for index, letter in enumerate(codes):
        r, c = divmod(index, COLS)
        polygon = [list(vertices[r][c]), list(vertices[r][c + 1]), list(vertices[r + 1][c + 1]), list(vertices[r + 1][c])]
        c_lat = round(sum(p[0] for p in polygon) / 4, 6)
        c_lng = round(sum(p[1] for p in polygon) / 4, 6)
        area_id = db.execute(
            "INSERT INTO areas (code, name, polygon, centroid_lat, centroid_lng, is_synthetic) VALUES (?,?,?,?,?,1)",
            (f"KV-{letter}", f"Khu vực {letter}", db.dumps(polygon), c_lat, c_lng))
        areas[letter] = {"id": area_id, "polygon": polygon}

    # --- Thời tiết 35 ngày ---------------------------------------------
    start = today - timedelta(days=DAYS - 1)
    with db.session() as conn:
        for letter, (rain_now, rain_prev, temp, hum, _, _) in PROFILES.items():
            weekly = [rain_prev * rng.uniform(0.5, 0.9), rain_prev * rng.uniform(0.6, 1.0),
                      rain_prev * rng.uniform(0.7, 1.1), rain_prev, rain_now]
            rain_days: list[float] = []
            for total in weekly:
                rain_days += _spread(round(total, 1), 7, rng)
            temps = _around(temp - 0.6, DAYS - 7, 1.4, rng) + _around(temp, 7, 1.2, rng)
            base_hum = hum if hum is not None else 77
            hums = _around(base_hum - 3, DAYS - 7, 5, rng) + _around(base_hum, 7, 4, rng)
            for i in range(DAYS):
                day = start + timedelta(days=i)
                humidity = hums[i]
                # Khu vực D: cảm biến độ ẩm không có số liệu 10 ngày gần nhất (tình huống thiếu dữ liệu)
                if hum is None and i >= DAYS - 10:
                    humidity = None
                conn.execute(
                    "INSERT INTO weather (area_id, obs_date, rainfall_mm, temperature_c, humidity_pct, source, batch_id) VALUES (?,?,?,?,?,?,?)",
                    (areas[letter]["id"], day.isoformat(), rain_days[i], temps[i], humidity, SOURCE, "SEED"))

        # --- Điểm nước đọng và khảo sát --------------------------------
        wp_no = sv_no = 0
        for letter, (_, _, _, _, n_water, survey_results) in PROFILES.items():
            polygon = areas[letter]["polygon"]
            resolved = 2 if n_water >= 9 else 1 if n_water >= 5 else 0
            for k in range(n_water + resolved):
                wp_no += 1
                lat, lng = _random_point(polygon, rng)
                status = "active" if k < n_water else "resolved"
                observed = today - timedelta(days=rng.randint(1, 6) if status == "active" else rng.randint(9, 20))
                conn.execute(
                    """INSERT INTO water_points (code, area_id, latitude, longitude, water_type, status, persistence_days,
                       observed_date, notes, source, batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"WP-{wp_no:04d}", areas[letter]["id"], lat, lng, rng.choice(WATER_TYPES), status,
                     rng.randint(2, 12), observed.isoformat(), None, SOURCE, "SEED"))
            for result in survey_results:
                sv_no += 1
                lat, lng = _random_point(polygon, rng)
                count = rng.randint(3, 25) if result in ("larvae_present", "adult_present") else 0 if result == "none_found" else None
                conn.execute(
                    """INSERT INTO surveys (code, area_id, latitude, longitude, survey_date, species, result, vector_count,
                       notes, entered_by, source, batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"SV-{sv_no:04d}", areas[letter]["id"], lat, lng, (today - timedelta(days=rng.randint(1, 12))).isoformat(),
                     "aedes", result, count, None, "Dữ liệu mẫu", SOURCE, "SEED"))

    db.execute("""INSERT INTO import_batches (id, kind, filename, user_name, created_at, rows_added, rows_updated, rows_rejected, rows_skipped)
                  VALUES ('SEED','all','(dữ liệu mẫu giả lập)','Hệ thống',?,?,0,0,0)""",
               (now, DAYS * len(PROFILES) + wp_no + sv_no))
    return True


if __name__ == "__main__":
    created = seed(reset="--reset" in sys.argv)
    print("Đã tạo dữ liệu mẫu giả lập." if created else "CSDL đã có dữ liệu — không seed lại (dùng --reset để tạo lại từ đầu).")
