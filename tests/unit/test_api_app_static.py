from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app


def test_api_app_serves_root_and_assets(tmp_path: Path) -> None:
    dist_path = tmp_path / "dist"
    assets_path = dist_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    (assets_path / "app.js").write_text("console.log('ok');", encoding="utf-8")

    client = TestClient(create_api_app(ui_dist_path=dist_path))

    root_response = client.get("/")
    asset_response = client.get("/assets/app.js")

    assert root_response.status_code == 200
    assert "dashboard" in root_response.text
    assert root_response.headers["cache-control"] == "no-cache"
    assert asset_response.status_code == 200
    assert "immutable" in asset_response.headers["cache-control"]


def test_api_app_accepts_head_for_root_and_deep_routes(tmp_path: Path) -> None:
    dist_path = tmp_path / "dist"
    assets_path = dist_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")

    client = TestClient(create_api_app(ui_dist_path=dist_path))

    root_response = client.head("/")
    deep_response = client.head("/dashboard")

    assert root_response.status_code == 200
    assert deep_response.status_code == 200


def test_api_app_uses_spa_fallback_for_deep_routes(tmp_path: Path) -> None:
    dist_path = tmp_path / "dist"
    assets_path = dist_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text("<html><body>spa-shell</body></html>", encoding="utf-8")

    client = TestClient(create_api_app(ui_dist_path=dist_path))

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "spa-shell" in response.text


def test_api_app_keeps_api_routes_available_with_ui_enabled(tmp_path: Path) -> None:
    dist_path = tmp_path / "dist"
    assets_path = dist_path / "assets"
    assets_path.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text("<html><body>spa-shell</body></html>", encoding="utf-8")

    client = TestClient(create_api_app(ui_dist_path=dist_path))

    response = client.get("/api/health/overview")

    assert response.status_code == 200
    assert response.json()["data"]["items"]
