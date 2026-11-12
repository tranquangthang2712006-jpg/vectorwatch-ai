"""Điểm vào FastAPI. Phục vụ API và (nếu đã build) giao diện tĩnh ở frontend/dist."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .agents import orchestrator
from .routers import agent, alerts, analysis, auth, dashboard, data, mapdata, meta, reports, tasks
from .seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed()
    orchestrator.recover_interrupted()
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    # Không trả stack trace ra giao diện.
    return JSONResponse({"detail": f"Máy chủ gặp lỗi nội bộ ({type(exc).__name__}). Hãy thử lại; nếu lỗi lặp lại, báo quản trị viên."},
                        status_code=500)


for module in (auth, agent, meta, dashboard, mapdata, data, analysis, tasks, alerts, reports):
    app.include_router(module.router)

if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Không tìm thấy API này.")
        target = config.FRONTEND_DIST / path
        if path and target.is_file() and config.FRONTEND_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(config.FRONTEND_DIST / "index.html")
