#!/usr/bin/env bash
# Chạy VectorWatch AI (backend phục vụ luôn giao diện đã build ở frontend/dist).
set -e
cd "$(dirname "$0")"
[ -f .env ] || { cp .env.example .env; echo "Đã tạo .env từ .env.example"; }
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
if [ ! -d .venv ]; then $PY -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
pip install -q -r backend/requirements.txt
cd backend
echo "Mở http://127.0.0.1:8000 trên trình duyệt (Ctrl+C để dừng)"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
