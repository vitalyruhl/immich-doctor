from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus
from immich_doctor.repair.paths import repair_manifests_root
from immich_doctor.repair.store import RepairJournalStore


def _generated_at() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class RepairVisibilityService:
    store: RepairJournalStore = field(default_factory=RepairJournalStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def list_runs(self, settings: AppSettings) -> dict[str, object]:
        items = []
        for run_id in self._list_run_ids(settings):
            run = self.store.load_run(settings, run_id)
            entries = self.store.load_journal_entries(settings, run_id)
            items.append(
                {
                    "repairRunId": run.repair_run_id,
                    "startedAt": run.started_at,
                    "endedAt": run.ended_at,
                    "scope": run.scope,
                    "status": run.status.value,
                    "preRepairSnapshotId": run.pre_repair_snapshot_id,
                    "postRepairSnapshotId": run.post_repair_snapshot_id,
                    "hasJournalEntries": bool(entries),
                    "journalEntryCount": len(entries),
                    "undoAvailable": any(entry.undo_type.value != "none" for entry in entries),
                }
            )
        items.sort(key=lambda item: item["startedAt"], reverse=True)
        return {"generatedAt": _generated_at(), "items": items}

    def get_run_detail(self, settings: AppSettings, repair_run_id: str) -> dict[str, object]:
        run = self.store.load_run(settings, repair_run_id)
        entries = self.store.load_journal_entries(settings, repair_run_id)
        return {
            "generatedAt": _generated_at(),
            "repairRun": {
                "repairRunId": run.repair_run_id,
                "startedAt": run.started_at,
                "endedAt": run.ended_at,
                "scope": run.scope,
                "status": run.status.value,
                "liveStateFingerprint": run.live_state_fingerprint,
                "planTokenId": run.plan_token_id,
                "preRepairSnapshotId": run.pre_repair_snapshot_id,
                "postRepairSnapshotId": run.post_repair_snapshot_id,
                "journalEntryCount": len(entries),
                "undoAvailable": any(entry.undo_type.value != "none" for entry in entries),
                "journalAvailable": bool(entries),
            },
            "journalEntries": [
                {
                    "entryId": entry.entry_id,
                    "createdAt": entry.created_at,
                    "operationType": entry.operation_type,
                    "status": entry.status.value,
                    "assetId": entry.asset_id,
                    "table": entry.table,
                    "originalPath": entry.original_path,
                    "quarantinePath": entry.quarantine_path,
                    "undoType": entry.undo_type.value,
                    "undoPayload": entry.undo_payload,
                    "errorDetails": entry.error_details,
                }
                for entry in entries
            ],
            "limitations": [
                "Undo visibility exists through persisted journal data.",
                "Full restore orchestration is not implemented yet.",
            ],
        }

    def quarantine_summary(self, settings: AppSettings) -> dict[str, object]:
        items = [
            item for item in self.store.load_quarantine_index(settings) if getattr(item, "state", "active") == "active"
        ]
        path_check = self.filesystem.validate_creatable_directory(
            "quarantine_path",
            settings.quarantine_path,
        )
        return {
            "generatedAt": _generated_at(),
            "path": str(settings.quarantine_path),
            "foundationState": self._ui_state(path_check.status),
            "pathSummary": path_check.message,
            "indexPresent": settings.quarantine_path.joinpath("index.jsonl").exists(),
            "itemCount": len(items),
            "workflowImplemented": False,
            "message": (
                "Quarantine indexing exists, but move/restore workflow is not implemented yet."
            ),
        }

    def _list_run_ids(self, settings: AppSettings) -> list[str]:
        root = repair_manifests_root(settings)
        if not root.exists():
            return []
        return sorted(path.parent.name for path in root.glob("*/run.json"))

    def _ui_state(self, status: CheckStatus) -> str:
        mapping = {
            CheckStatus.PASS: "ok",
            CheckStatus.WARN: "warning",
            CheckStatus.FAIL: "error",
            CheckStatus.SKIP: "unknown",
        }
        return mapping[status]
