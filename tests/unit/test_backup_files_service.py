from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupResult,
    BackupTarget,
    ResolvedBackupLocation,
)
from immich_doctor.backup.files.executor import FileBackupExecutionError
from immich_doctor.backup.orchestration.files_service import BackupFilesService
from immich_doctor.core.config import AppSettings


def test_backup_files_service_uses_context_started_at_for_versioning(tmp_path: Path) -> None:
    source_path = tmp_path / "library"
    target_path = tmp_path / "backup"
    source_path.mkdir()
    target_path.mkdir()

    captured: dict[str, object] = {}

    class Resolver:
        def resolve(self, context):
            captured["started_at"] = context.started_at
            captured["target_reference"] = context.target.reference
            return ResolvedBackupLocation(target=context.target, root_path=target_path)

    class Executor:
        def execute(self, plan):
            captured["backup_root_path"] = plan.backup_root_path
            return BackupResult(
                domain="backup.files",
                action="run",
                status="success",
                summary="ok",
                context=plan.request.context,
            )

    started_at = datetime(2026, 3, 14, 21, 30, tzinfo=UTC)
    service = BackupFilesService(
        location_resolver=Resolver(),
        executor=Executor(),
        clock=lambda: started_at,
    )
    settings = AppSettings(
        _env_file=None,
        immich_library_root=source_path,
        backup_target_path=target_path,
    )

    result = service.run(settings)

    assert result.status == "success"
    assert captured["started_at"] == started_at
    assert captured["target_reference"] == str(target_path)
    assert captured["backup_root_path"] == target_path / "20260314T213000Z"


def test_backup_files_service_uses_traceable_artifact_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "library"
    target_path = tmp_path / "backup"
    source_path.mkdir()
    target_path.mkdir()

    class Resolver:
        def resolve(self, context):
            return ResolvedBackupLocation(target=context.target, root_path=target_path)

    class Executor:
        def execute(self, plan):
            artifact_target = BackupTarget(
                kind="local",
                reference=str(plan.backup_root_path),
                display_name=plan.backup_root_path.name,
            )
            return BackupResult(
                domain="backup.files",
                action="run",
                status="success",
                summary="ok",
                context=plan.request.context,
                artifacts=(
                    BackupArtifact(
                        name=plan.request.source_label,
                        kind="file_archive",
                        target=artifact_target,
                        relative_path=plan.artifact_relative_path,
                    ),
                ),
            )

    service = BackupFilesService(
        location_resolver=Resolver(),
        executor=Executor(),
        clock=lambda: datetime(2026, 3, 14, 21, 30, tzinfo=UTC),
    )
    settings = AppSettings(
        _env_file=None,
        immich_library_root=source_path,
        backup_target_path=target_path,
    )

    result = service.run(settings)

    assert result.artifacts[0].relative_path == Path("files/immich-library")
    assert result.artifacts[0].target.reference == str(target_path / "20260314T213000Z")


def test_backup_files_service_returns_structured_failure_details(tmp_path: Path) -> None:
    source_path = tmp_path / "library"
    target_path = tmp_path / "backup"
    source_path.mkdir()
    target_path.mkdir()

    class Resolver:
        def resolve(self, context):
            return ResolvedBackupLocation(target=context.target, root_path=target_path)

    class Executor:
        def execute(self, plan):
            raise FileBackupExecutionError(
                message="Rsync execution failed with exit code 23.",
                argv=("rsync", "--archive"),
                exit_code=23,
                stdout="",
                stderr="partial transfer",
            )

    service = BackupFilesService(
        location_resolver=Resolver(),
        executor=Executor(),
        clock=lambda: datetime(2026, 3, 14, 21, 30, tzinfo=UTC),
    )
    settings = AppSettings(
        _env_file=None,
        immich_library_root=source_path,
        backup_target_path=target_path,
    )

    result = service.run(settings)

    assert result.status == "fail"
    assert result.details["error"]["exit_code"] == 23
    assert result.details["resolved_location"]["root_path"] == target_path.as_posix()


def test_backup_files_service_fails_when_required_paths_are_missing() -> None:
    service = BackupFilesService(clock=lambda: datetime(2026, 3, 14, 21, 30, tzinfo=UTC))
    settings = AppSettings(_env_file=None)

    result = service.run(settings)

    assert result.status == "fail"
    assert result.summary == "File backup configuration is invalid."
    assert len(result.details["issues"]) == 2
