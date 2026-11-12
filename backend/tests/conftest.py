"""Dùng CSDL tạm riêng cho test để không đụng dữ liệu demo."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["VW_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ.setdefault("VW_DEMO_PASSWORD", "test-only-password")
os.environ["VW_STEP_DELAY"] = "0"

import pytest  # noqa: E402

from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    seed()
