from __future__ import annotations

import json

from immich_doctor.consistency.missing_asset_models import MissingAssetRestorePoint
from immich_doctor.core.config import AppSettings
from immich_doctor.repair.paths import (
    missing_asset_restore_point_file,
    missing_asset_restore_point_index_file,
    missing_asset_restore_points_root,
)


class MissingAssetRestorePointStore:
    def create(self, settings: AppSettings, restore_point: MissingAssetRestorePoint) -> None:
        root = missing_asset_restore_points_root(settings)
        root.mkdir(parents=True, exist_ok=True)
        payload = restore_point.to_dict()
        missing_asset_restore_point_file(settings, restore_point.restore_point_id).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        items = self.list_points(settings)
        items = [item for item in items if item.restore_point_id != restore_point.restore_point_id]
        items.append(restore_point)
        self._write_index(settings, items)

    def list_points(self, settings: AppSettings) -> list[MissingAssetRestorePoint]:
        index_path = missing_asset_restore_point_index_file(settings)
        if not index_path.exists():
            return []
        rows: list[MissingAssetRestorePoint] = []
        with index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(MissingAssetRestorePoint.from_dict(json.loads(line)))
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows

    def load(self, settings: AppSettings, restore_point_id: str) -> MissingAssetRestorePoint:
        payload = json.loads(
            missing_asset_restore_point_file(settings, restore_point_id).read_text(encoding="utf-8")
        )
        return MissingAssetRestorePoint.from_dict(payload)

    def update(self, settings: AppSettings, restore_point: MissingAssetRestorePoint) -> None:
        self.create(settings, restore_point)

    def delete(self, settings: AppSettings, restore_point_ids: tuple[str, ...]) -> list[str]:
        deleted: list[str] = []
        remaining: list[MissingAssetRestorePoint] = []
        requested = set(restore_point_ids)
        for item in self.list_points(settings):
            if item.restore_point_id not in requested:
                remaining.append(item)
                continue
            point_path = missing_asset_restore_point_file(settings, item.restore_point_id)
            if point_path.exists():
                point_path.unlink()
            deleted.append(item.restore_point_id)
        self._write_index(settings, remaining)
        return deleted

    def _write_index(
        self,
        settings: AppSettings,
        items: list[MissingAssetRestorePoint],
    ) -> None:
        root = missing_asset_restore_points_root(settings)
        root.mkdir(parents=True, exist_ok=True)
        index_path = missing_asset_restore_point_index_file(settings)
        with index_path.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item.to_dict(), sort_keys=True) + "\n")
