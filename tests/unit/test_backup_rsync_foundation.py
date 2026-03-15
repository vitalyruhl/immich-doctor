from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from immich_doctor.backup.core.models import BackupContext, BackupTarget, ResolvedBackupLocation
from immich_doctor.backup.files import (
    FileBackupExecutionError,
    FileBackupRequest,
    LocalFileBackupExecutor,
    RsyncCommandBuilder,
    VersionedDestinationBuilder,
)


def build_request(tmp_path: Path) -> FileBackupRequest:
    target = BackupTarget(kind="local", reference=str(tmp_path / "backups"), display_name="Local")
    context = BackupContext(
        job_name="files-backup",
        requested_components=("files",),
        target=target,
        started_at=datetime(2026, 3, 14, 20, 0, tzinfo=UTC),
    )
    return FileBackupRequest(
        context=context,
        location=ResolvedBackupLocation(target=target, root_path=tmp_path / "backups"),
        source_path=tmp_path / "source",
        source_label="Immich Uploads",
    )


def test_versioned_destination_builder_creates_deterministic_structure(tmp_path: Path) -> None:
    request = build_request(tmp_path)

    plan = VersionedDestinationBuilder().build(request)

    assert plan.destination_path == (
        tmp_path / "backups" / "20260314T200000Z" / "files" / "immich-uploads"
    )
    assert plan.backup_root_path == tmp_path / "backups" / "20260314T200000Z"
    assert plan.artifact_relative_path == Path("files/immich-uploads")


def test_rsync_builder_uses_safe_default_flags(tmp_path: Path) -> None:
    request = build_request(tmp_path)
    plan = VersionedDestinationBuilder().build(request)

    command = RsyncCommandBuilder().build(plan)

    assert command.argv[0] == "rsync"
    assert "--archive" in command.argv
    assert "--hard-links" in command.argv
    assert "--numeric-ids" in command.argv
    assert "--delete" not in command.argv
    assert "--remove-source-files" not in command.argv
    assert command.argv[-2].endswith("/source/")


def test_rsync_builder_rejects_destructive_options() -> None:
    with pytest.raises(ValueError, match="Destructive rsync flags"):
        RsyncCommandBuilder(extra_options=("--delete",))


def test_local_executor_returns_structural_backup_result(tmp_path: Path, monkeypatch) -> None:
    request = build_request(tmp_path)
    source_path = request.source_path
    source_path.mkdir(parents=True)
    (source_path / "asset.jpg").write_text("data", encoding="utf-8")
    plan = VersionedDestinationBuilder().build(request)

    captured: dict[str, tuple[str, ...]] = {}

    def fake_run(
        argv: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        plan.destination_path.mkdir(parents=True, exist_ok=True)
        (plan.destination_path / "asset.jpg").write_text("data", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    executor = LocalFileBackupExecutor(command_runner=fake_run)
    monkeypatch.setattr("shutil.which", lambda executable: executable)

    result = executor.execute(plan)

    assert captured["argv"][0] == "rsync"
    assert result.domain == "backup.files"
    assert result.status == "success"
    assert result.artifacts[0].relative_path == Path("files/immich-uploads")
    assert result.artifacts[0].target.reference == str(plan.backup_root_path)
    assert (plan.destination_path / "asset.jpg").exists()


def test_local_executor_reports_missing_rsync(tmp_path: Path, monkeypatch) -> None:
    request = build_request(tmp_path)
    plan = VersionedDestinationBuilder().build(request)
    executor = LocalFileBackupExecutor()
    monkeypatch.setattr("shutil.which", lambda executable: None)

    with pytest.raises(FileBackupExecutionError, match="Required executable is not available"):
        executor.execute(plan)
