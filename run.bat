@echo off
rem Chay VectorWatch AI tren Windows
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt
cd backend
echo Mo http://127.0.0.1:8000 tren trinh duyet (Ctrl+C de dung)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
