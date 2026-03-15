from __future__ import annotations

from fastapi import FastAPI

from immich_doctor.api.routes.health import health_router


def create_api_app() -> FastAPI:
    app = FastAPI(title="immich-doctor API", version="0.1.0")
    app.include_router(health_router, prefix="/api")
    return app
