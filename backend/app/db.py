"""Lớp truy cập SQLite tối giản (stdlib). Có thể thay bằng PostgreSQL/PostGIS ở giai đoạn sau."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    polygon TEXT NOT NULL,            -- JSON [[lat,lng],...]
    centroid_lat REAL NOT NULL,
    centroid_lng REAL NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS weather (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL,
    obs_date TEXT NOT NULL,
    rainfall_mm REAL,
    temperature_c REAL,
    humidity_pct REAL,
    source TEXT NOT NULL,
    batch_id TEXT,
    UNIQUE(area_id, obs_date)
);
CREATE TABLE IF NOT EXISTS water_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    area_id INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    water_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    persistence_days INTEGER,
    observed_date TEXT NOT NULL,
    notes TEXT,
    source TEXT NOT NULL,
    batch_id TEXT
);
CREATE TABLE IF NOT EXISTS surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    area_id INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    survey_date TEXT NOT NULL,
    species TEXT NOT NULL,
    result TEXT NOT NULL,             -- larvae_present | adult_present | none_found | not_surveyed
    vector_count INTEGER,
    notes TEXT,
    entered_by TEXT,
    source TEXT NOT NULL,
    batch_id TEXT
);
CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    filename TEXT,
    user_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rows_added INTEGER NOT NULL,
    rows_updated INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    rows_skipped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL,
    species TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    ess REAL,
    ess_class TEXT,
    pis REAL,
    pis_class TEXT,
    completeness REAL,
    scoring_version TEXT NOT NULL,
    payload TEXT NOT NULL,            -- JSON đầy đủ: đầu vào, tham số, thành phần, giải thích
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    task_id TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    params TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    plan TEXT,
    result TEXT,
    error TEXT,
    llm_mode TEXT NOT NULL,
    is_test INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    cancelled_by TEXT,
    cancel_reason TEXT
);
CREATE TABLE IF NOT EXISTS task_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    step_key TEXT NOT NULL,
    agent TEXT NOT NULL,
    tool TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    input TEXT NOT NULL,
    output TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT,                         -- mã nhiệm vụ hoặc mã tin nhắn trợ lý
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT,
    status TEXT NOT NULL,             -- success | error | rejected (bị loại bởi kiểm tra đầu ra)
    error_code TEXT,
    output_chars INTEGER,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,               -- user | assistant
    content TEXT NOT NULL,
    payload TEXT,                     -- JSON: ý định, bảng số liệu, truy vết công cụ, xác minh
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    area_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,             -- pending | approved | rejected | needs_revision
    ess REAL,
    pis REAL,
    reasons TEXT NOT NULL,
    factors TEXT NOT NULL,
    sources TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    assignee TEXT,
    origin TEXT NOT NULL,             -- agent | manual
    task_id TEXT,
    run_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS test_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_run_id TEXT NOT NULL,
    case_code TEXT NOT NULL,
    title TEXT NOT NULL,
    input TEXT NOT NULL,
    expected TEXT NOT NULL,
    actual TEXT NOT NULL,
    passed INTEGER NOT NULL,
    comment TEXT,
    duration_ms INTEGER,
    run_at TEXT NOT NULL,
    run_by TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with session() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with session() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default
