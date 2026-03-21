from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_runtime_capability_service import (
    BackupRuntimeCapabilityService,
)


def test_backup_runtime_capability_service_records_rsync_presence(monkeypatch, tmp_path: Path) -> None:
    runtime = BackgroundJobRuntime()
    try:
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.PASS,
                message="Required external tool is available in the runtime.",
                details={"tool": tool, "path": "/usr/bin/rsync", "version": "rsync 3.2.7"},
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_rsync()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is True
    assert snapshot["check"]["details"]["version"] == "rsync 3.2.7"


def test_backup_runtime_capability_service_records_rsync_absence(monkeypatch, tmp_path: Path) -> None:
    runtime = BackgroundJobRuntime()
    try:
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.FAIL,
                message="Required external tool `rsync` is not available on PATH.",
                details={"tool": tool},
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_rsync()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is False
    assert "not available" in snapshot["summary"]
