from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from immich_doctor.api.routes.backup import backup_router
from immich_doctor.api.routes.health import health_router
from immich_doctor.api.routes.repair import repair_router
from immich_doctor.api.routes.restore import restore_router
from immich_doctor.api.routes.runtime import runtime_router
from immich_doctor.api.routes.settings import settings_router

DEFAULT_UI_DIST_PATH = Path("/app/ui/dist")
REPO_UI_DIST_PATH = Path(__file__).resolve().parents[2] / "ui" / "frontend" / "dist"


def create_api_app(ui_dist_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="immich-doctor API", version="0.1.0")
    app.include_router(backup_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(repair_router, prefix="/api")
    app.include_router(restore_router, prefix="/api")
    app.include_router(runtime_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    dist_path = _resolve_ui_dist_path(ui_dist_path)
    if dist_path is not None:
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")
        _register_ui_routes(app, dist_path)
    else:
        _register_unavailable_ui_routes(app)

    @app.middleware("http")
    async def set_cache_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        elif request.url.path == "/" and response.status_code == 200:
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    return app


def _resolve_ui_dist_path(ui_dist_path: Path | None) -> Path | None:
    if ui_dist_path is not None:
        return ui_dist_path

    env_path = os.getenv("IMMICH_DOCTOR_UI_DIST_PATH")
    candidates = [
        Path(env_path) if env_path else None,
        DEFAULT_UI_DIST_PATH,
        REPO_UI_DIST_PATH,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        if (candidate / "index.html").exists() and (candidate / "assets").is_dir():
            return candidate
    return None


def _register_ui_routes(app: FastAPI, dist_path: Path) -> None:
    index_path = dist_path / "index.html"

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    def serve_root() -> Response:
        return FileResponse(index_path, media_type="text/html")

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
        response_model=None,
    )
    def serve_spa(full_path: str) -> Response:
        if not full_path:
            return FileResponse(index_path, media_type="text/html")
        if full_path.startswith("api/") or full_path == "api":
            return PlainTextResponse("Not Found", status_code=404)

        requested_path = (dist_path / full_path).resolve()
        if _is_within_directory(requested_path, dist_path) and requested_path.is_file():
            return FileResponse(requested_path)

        return FileResponse(index_path, media_type="text/html")


def _register_unavailable_ui_routes(app: FastAPI) -> None:
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    def ui_not_available() -> Response:
        return HTMLResponse(
            "<h1>immich-doctor UI is not available</h1><p>Static frontend files are missing.</p>",
            status_code=503,
        )

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
        response_model=None,
    )
    def ui_not_available_spa(full_path: str) -> Response:
        if full_path.startswith("api/") or full_path == "api":
            return PlainTextResponse("Not Found", status_code=404)
        return HTMLResponse(
            "<h1>immich-doctor UI is not available</h1><p>Static frontend files are missing.</p>",
            status_code=503,
        )


def _is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory.resolve())
    except ValueError:
        return False
    return True


app = create_api_app()
