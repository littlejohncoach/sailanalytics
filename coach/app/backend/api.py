from __future__ import annotations

from fastapi import FastAPI

from .routes.races import router as races_router
from .routes.data import router as data_router
from .routes.tracks import router as tracks_router
from .routes.analytics import router as analytics_router   # ← NEW (replaces both)
from .routes.geometry import router as geometry_router
from .routes.race_metadata import router as race_metadata_router


def register_routes(app: FastAPI) -> None:
    """
    Pattern A (canonical):
      - api.py owns the /api namespace
      - route modules must NOT define prefix="/api"
    """

    app.include_router(races_router, prefix="/api")
    app.include_router(data_router, prefix="/api")
    app.include_router(tracks_router, prefix="/api")

    # unified analytics (total race + leg)
    app.include_router(analytics_router, prefix="/api")

    app.include_router(geometry_router, prefix="/api")
    app.include_router(race_metadata_router, prefix="/api")