from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import register_routes


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store"
        return resp


def create_app() -> FastAPI:
    app = FastAPI(title="SailAnalytics Coach Dashboard", version="0.1.0")

    # Register all API routes (/api/...)
    register_routes(app)

    # Serve frontend files under /static/*
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    app.mount("/static", NoCacheStaticFiles(directory=str(frontend_dir)), name="static")

    # Silence harmless favicon 404 noise
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    # Serve the UI
    @app.get("/", tags=["default"])
    def index(_: Request):
        resp = FileResponse(str(frontend_dir / "index.html"))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


# 👇 REQUIRED FOR RENDER / UVICORN
app = create_app()