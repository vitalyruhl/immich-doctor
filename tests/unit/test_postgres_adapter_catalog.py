from __future__ import annotations

from typing import Any

from immich_doctor.adapters import postgres as postgres_module
from immich_doctor.adapters.postgres import PostgresAdapter


def test_catalog_asset_listing_projects_null_encoded_video_path_when_column_is_absent(
    monkeypatch,
) -> None:
    adapter = PostgresAdapter()

    def fake_list_columns(*args: Any, **kwargs: Any) -> list[dict[str, object]]:
        del args, kwargs
        return [
            {"column_name": "id"},
            {"column_name": "type"},
            {"column_name": "ownerId"},
            {"column_name": "createdAt"},
            {"column_name": "updatedAt"},
            {"column_name": "originalFileName"},
            {"column_name": "originalPath"},
            {"column_name": "checksumAlgorithm"},
        ]

    def fake_fetch_all_composed(*args: Any, **kwargs: Any) -> list[dict[str, object]]:
        del kwargs
        query = args[2]
        query_repr = repr(query)
        assert "NULL::text" in query_repr
        assert "encodedVideoPath" in query_repr
        assert "checksumAlgorithm" in query_repr
        return [{"id": "asset-1", "encodedVideoPath": None}]

    monkeypatch.setattr(adapter, "list_columns", fake_list_columns)
    monkeypatch.setattr(postgres_module, "fetch_all_composed", fake_fetch_all_composed)

    rows = adapter.list_all_assets_for_catalog_consistency(
        "postgresql://postgres:postgres@localhost:5432/immich",
        3,
    )

    assert rows == [{"id": "asset-1", "encodedVideoPath": None}]
