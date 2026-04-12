from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from immich_doctor.catalog.paths import (
    catalog_ignored_findings_path,
    catalog_remediation_cache_path,
    catalog_root,
)
from immich_doctor.catalog.remediation_models import CatalogIgnoredFinding
from immich_doctor.core.config import AppSettings


class CatalogRemediationStateStore:
    def load_cached_findings(self, settings: AppSettings) -> dict[str, Any] | None:
        path = catalog_remediation_cache_path(settings)
        if not path.exists():
            return None
        return self._read_json(path)

    def save_cached_findings(self, settings: AppSettings, payload: dict[str, Any]) -> None:
        self._write_json(catalog_remediation_cache_path(settings), payload)

    def load_ignored_findings(self, settings: AppSettings) -> list[CatalogIgnoredFinding]:
        path = catalog_ignored_findings_path(settings)
        if not path.exists():
            return []
        payload = self._read_json(path)
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            return []
        return [CatalogIgnoredFinding.from_dict(item) for item in rows if isinstance(item, dict)]

    def save_ignored_findings(
        self,
        settings: AppSettings,
        items: list[CatalogIgnoredFinding],
    ) -> None:
        self._write_json(
            catalog_ignored_findings_path(settings),
            {"items": [item.to_dict() for item in items]},
        )

    def ensure_foundation(self, settings: AppSettings) -> None:
        catalog_root(settings).mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
