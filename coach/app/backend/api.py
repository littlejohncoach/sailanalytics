from __future__ import annotations

from fastapi import FastAPI

from .routes.races import router as races_router
from .routes.data import router as data_router
from .routes.tracks import router as tracks_router
from .routes.total_race_analytics import router as total_race_analytics_router
from .routes.leg_analytics import router as leg_analytics_router
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
    app.include_router(total_race_analytics_router, prefix="/api")
    app.include_router(leg_analytics_router, prefix="/api")
    app.include_router(geometry_router, prefix="/api")
    app.include_router(race_metadata_router, prefix="/api")