from __future__ import annotations

import json
from pathlib import Path

from immich_doctor.backup.core.models import BackupSnapshot
from immich_doctor.backup.core.paths import backup_snapshot_manifest_path, backup_snapshot_root
from immich_doctor.core.config import AppSettings


class BackupSnapshotStore:
    def persist_snapshot(self, settings: AppSettings, snapshot: BackupSnapshot) -> BackupSnapshot:
        path = backup_snapshot_manifest_path(settings, snapshot.snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return BackupSnapshot.from_dict(
            {
                **snapshot.to_dict(),
                "manifest_path": path.as_posix(),
            }
        )

    def load_snapshot(self, settings: AppSettings, snapshot_id: str) -> BackupSnapshot:
        path = backup_snapshot_manifest_path(settings, snapshot_id)
        return BackupSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_snapshots(self, settings: AppSettings) -> list[BackupSnapshot]:
        return [
            self.load_snapshot_from_path(path)
            for path in self.list_snapshot_manifest_paths(settings)
        ]

    def list_snapshot_manifest_paths(self, settings: AppSettings) -> list[Path]:
        root = backup_snapshot_root(settings)
        if not root.exists():
            return []
        return sorted(root.glob("*.json"))

    def load_snapshot_from_path(self, path: Path) -> BackupSnapshot:
        return BackupSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
