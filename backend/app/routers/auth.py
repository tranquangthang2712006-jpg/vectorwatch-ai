"""Đăng nhập và thông tin người dùng hiện tại."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..security import ROLES, create_token, current_user, public_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody):
    user = db.query_one("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Email hoặc mật khẩu không đúng. Kiểm tra lại tài khoản demo trong README.")
    return {"token": create_token(user), "user": public_user(user)}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user


@router.get("/demo-accounts")
def demo_accounts():
    """Danh sách email tài khoản demo (không kèm mật khẩu) để hiển thị ở màn hình đăng nhập."""
    rows = db.query("SELECT email, full_name, role FROM users ORDER BY id")
    return [{**r, "role_label": ROLES.get(r["role"], r["role"])} for r in rows]
