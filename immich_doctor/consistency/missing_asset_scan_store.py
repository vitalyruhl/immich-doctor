from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from immich_doctor.consistency.missing_asset_models import (
    MissingAssetCompletedScanSummary,
    MissingAssetScanFailureKind,
    MissingAssetScanJob,
    MissingAssetScanState,
)
from immich_doctor.core.config import AppSettings


def missing_asset_scan_root(settings: AppSettings) -> Path:
    return settings.manifests_path / "consistency" / "missing-asset-references"


def missing_asset_scan_state_file(settings: AppSettings) -> Path:
    return missing_asset_scan_root(settings) / "scan-state.json"


def missing_asset_latest_completed_summary_file(settings: AppSettings) -> Path:
    return missing_asset_scan_root(settings) / "latest-completed-summary.json"


def missing_asset_latest_completed_snapshot_file(settings: AppSettings) -> Path:
    return missing_asset_scan_root(settings) / "latest-completed-snapshot.json"


class MissingAssetScanStore:
    def __init__(self) -> None:
        self._lock = Lock()

    def load_state(self, settings: AppSettings) -> MissingAssetScanJob | None:
        with self._lock:
            path = missing_asset_scan_state_file(settings)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            failure_kind = payload.get("failure_kind")
            return MissingAssetScanJob(
                scan_id=str(payload["scan_id"]),
                state=MissingAssetScanState(str(payload["state"])),
                requested_at=str(payload["requested_at"]),
                updated_at=str(payload["updated_at"]),
                started_at=self._optional_string(payload.get("started_at")),
                finished_at=self._optional_string(payload.get("finished_at")),
                summary=str(payload.get("summary") or ""),
                result_count=int(payload.get("result_count") or 0),
                scanned_asset_count=int(payload.get("scanned_asset_count") or 0),
                error_message=self._optional_string(payload.get("error_message")),
                failure_kind=(
                    MissingAssetScanFailureKind(str(failure_kind))
                    if isinstance(failure_kind, str) and failure_kind
                    else None
                ),
            )

    def save_state(self, settings: AppSettings, job: MissingAssetScanJob) -> MissingAssetScanJob:
        with self._lock:
            self._write_json(missing_asset_scan_state_file(settings), job.to_dict())
            return job

    def load_latest_completed_summary(
        self,
        settings: AppSettings,
    ) -> MissingAssetCompletedScanSummary | None:
        with self._lock:
            path = missing_asset_latest_completed_summary_file(settings)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return MissingAssetCompletedScanSummary(
                scan_id=str(payload["scan_id"]),
                status=str(payload["status"]),
                summary=str(payload["summary"]),
                generated_at=str(payload["generated_at"]),
                completed_at=str(payload["completed_at"]),
                finding_count=int(payload.get("finding_count") or 0),
                missing_on_disk_count=int(payload.get("missing_on_disk_count") or 0),
                ready_count=int(payload.get("ready_count") or 0),
                blocked_count=int(payload.get("blocked_count") or 0),
            )

    def load_latest_completed_snapshot(self, settings: AppSettings) -> dict[str, Any] | None:
        with self._lock:
            path = missing_asset_latest_completed_snapshot_file(settings)
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def save_latest_completed(
        self,
        settings: AppSettings,
        *,
        summary: MissingAssetCompletedScanSummary,
        snapshot: dict[str, Any],
    ) -> None:
        with self._lock:
            self._write_json(missing_asset_latest_completed_snapshot_file(settings), snapshot)
            self._write_json(
                missing_asset_latest_completed_summary_file(settings),
                summary.to_dict(),
            )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
