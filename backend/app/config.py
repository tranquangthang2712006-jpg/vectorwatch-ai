"""Cấu hình ứng dụng. Mọi giá trị nhạy cảm đọc từ biến môi trường / file .env, không ghi trong mã nguồn."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


def _load_env_file() -> None:
    """Đọc file .env ở thư mục gốc (nếu có) mà không cần thêm thư viện."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

APP_NAME = "VectorWatch AI"
APP_VERSION = "0.1.0-mvp"

DB_PATH = Path(os.environ.get("VW_DB_PATH", BACKEND_DIR / "data" / "vectorwatch.db"))
# Khóa ký token. Nếu không cấu hình, sinh ngẫu nhiên mỗi lần khởi động (token cũ hết hiệu lực).
SECRET_KEY = os.environ.get("VW_SECRET_KEY") or secrets.token_hex(32)
# Mật khẩu chung của các tài khoản demo. Nếu không cấu hình, sinh ngẫu nhiên và in ra console khi seed.
DEMO_PASSWORD = os.environ.get("VW_DEMO_PASSWORD")
TOKEN_TTL_HOURS = int(os.environ.get("VW_TOKEN_TTL_HOURS", "12"))
# Độ trễ (giây) giữa các bước workflow để người xem theo dõi được tiến trình trên giao diện.
STEP_DELAY = float(os.environ.get("VW_STEP_DELAY", "0.9"))
# Nhà cung cấp LLM: "simulated" (mặc định, theo luật) hoặc "openai_compatible" (API kiểu OpenAI /chat/completions).
LLM_PROVIDER = os.environ.get("VW_LLM_PROVIDER") or "simulated"
LLM_BASE_URL = os.environ.get("VW_LLM_BASE_URL") or "https://api.openai.com/v1"
LLM_MODEL = (os.environ.get("VW_LLM_MODEL") or "").strip()
# Khóa API chỉ đọc từ biến môi trường / .env; không ghi vào mã nguồn, log, CSDL hay giao diện.
LLM_API_KEY = (os.environ.get("VW_LLM_API_KEY") or "").strip()
LLM_TIMEOUT = float(os.environ.get("VW_LLM_TIMEOUT") or 20)
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

SAMPLE_SOURCE_LABEL = "Dữ liệu mẫu giả lập (seed v1)"
