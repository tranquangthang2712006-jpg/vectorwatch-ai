"""Xác thực (token ký HMAC) và phân quyền theo vai trò."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from . import config, db

ROLES = {
    "admin": "Quản trị hệ thống",
    "analyst": "Chuyên viên phân tích",
    "officer": "Cán bộ giám sát (người duyệt)",
    "viewer": "Người xem / Giám khảo",
}

# Người tạo đề xuất (analyst) không tự duyệt; viewer chỉ xem.
PERMISSIONS = {
    "admin": {"data.write", "analysis.run", "task.create", "alert.create", "alert.approve", "report.export", "tests.run"},
    "analyst": {"data.write", "analysis.run", "task.create", "alert.create", "report.export", "tests.run"},
    "officer": {"data.write", "analysis.run", "task.create", "alert.create", "alert.approve", "report.export"},
    "viewer": set(),
}

PERMISSION_LABELS = {
    "data.write": "nhập/sửa dữ liệu",
    "analysis.run": "chạy phân tích",
    "task.create": "tạo nhiệm vụ Agent",
    "alert.create": "tạo đề xuất kiểm tra",
    "alert.approve": "phê duyệt đề xuất",
    "report.export": "xuất báo cáo",
    "tests.run": "chạy bộ test case",
}


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(candidate.hex(), digest_hex)


def _sign(body: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()


def create_token(user: dict) -> str:
    payload = {"uid": user["id"], "exp": int(time.time()) + config.TOKEN_TTL_HOURS * 3600}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{body}.{_sign(body)}"


def _decode_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode()))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "role_label": ROLES.get(user["role"], user["role"]),
        "permissions": sorted(PERMISSIONS.get(user["role"], set())),
    }


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bạn chưa đăng nhập. Hãy đăng nhập để tiếp tục.")
    payload = _decode_token(authorization.split(" ", 1)[1])
    if not payload:
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Hãy đăng nhập lại.")
    user = db.query_one("SELECT * FROM users WHERE id=?", (payload["uid"],))
    if not user:
        raise HTTPException(401, "Tài khoản không còn tồn tại. Hãy đăng nhập lại.")
    return public_user(user)


def has_permission(user: dict, permission: str) -> bool:
    return permission in PERMISSIONS.get(user["role"], set())


def check_permission(user: dict, permission: str) -> None:
    """Ném HTTPException 403 nếu vai trò không có quyền. Dùng được cả ngoài ngữ cảnh request (test case)."""
    if not has_permission(user, permission):
        label = PERMISSION_LABELS.get(permission, permission)
        raise HTTPException(
            403,
            f"Vai trò “{ROLES.get(user['role'], user['role'])}” không có quyền {label}. "
            "Hãy liên hệ quản trị viên hoặc đăng nhập bằng tài khoản có quyền phù hợp.",
        )


def require(permission: str):
    def dependency(user: dict = Depends(current_user)) -> dict:
        check_permission(user, permission)
        return user

    return dependency
