from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.backup.core.models import BackupSnapshot
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.verify.service import snapshot_consistency_error
from immich_doctor.core.config import AppSettings


def summarize_backup_snapshot(snapshot: BackupSnapshot) -> dict[str, object]:
    consistency_error = snapshot_consistency_error(snapshot)
    return {
        "snapshotId": snapshot.snapshot_id,
        "createdAt": snapshot.created_at.isoformat(),
        "kind": snapshot.kind.value,
        "coverage": snapshot.coverage.value,
        "repairRunId": snapshot.repair_run_id,
        "verified": snapshot.verified,
        "manifestPath": snapshot.manifest_path.as_posix(),
        "fileArtifactCount": len(snapshot.file_artifacts),
        "hasDbArtifact": snapshot.db_artifact is not None,
        "basicValidity": "valid" if consistency_error is None else "invalid",
        "validityMessage": consistency_error or "Snapshot metadata is structurally valid.",
    }


@dataclass(slots=True)
class BackupSnapshotVisibilityService:
    store: BackupSnapshotStore = field(default_factory=BackupSnapshotStore)

    def list_snapshots(self, settings: AppSettings) -> dict[str, object]:
        snapshots = self.store.list_snapshots(settings)
        items = [summarize_backup_snapshot(snapshot) for snapshot in snapshots]
        items.sort(key=lambda item: item["createdAt"], reverse=True)
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "items": items,
            "limitations": [
                "Current executable snapshot creation is files-only.",
                "Restore orchestration is not implemented yet.",
            ],
        }
